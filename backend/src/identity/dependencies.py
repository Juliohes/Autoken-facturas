"""Dependencia de identidad por petición: valida el JWT y abre el contexto de aislamiento (S1.3).

Regla dura del sprint (§1 de la spec): el **token identifica**, pero el **subdominio aísla**. Esta
dependencia valida el access token, exige que su `tenant_id` case con el tenant del subdominio
(S1.2) y, si casa, abre `tenant_session` para que la petición corra dentro de la RLS del tenant:

- sin cabecera `Authorization` o con firma/formato inválidos -> **401**;
- el subdominio no resuelve a un tenant activo (p. ej. suspendido) -> **401** (no hay contexto);
- el `tenant_id` del token no casa con el tenant del subdominio -> **403** (token de otra asesoría).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from identity.repository import CompanyRef, MisconfiguredUserCompany, resolve_user_company
from identity.scoping import RlsScope, RoleNotAuthorized, scope_for_role
from identity.tokens import InvalidAccessToken, decode_access_token
from shared.config import get_settings
from shared.db import tenant_session
from tenancy.resolution import ResolvedTenant


@dataclass(frozen=True)
class AuthContext:
    """Identidad validada de la petición + la sesión de BD abierta en su contexto de tenant.

    `company` es la empresa del `user` (contexto de empresa, `app.company_id` fijado); es `None`
    para un `tenant_admin` (contexto de asesoría, ve todo el tenant). Ver spec S1.6.
    """

    user_id: UUID
    tenant_id: UUID
    role: str
    tenant_slug: str
    session: AsyncSession
    company: CompanyRef | None


async def current_identity(request: Request) -> AsyncIterator[AuthContext]:
    """Valida el token, lo casa con el subdominio y cede una sesión dentro de `tenant_session`.

    Según el rol, fija el nivel de empresa de la RLS (ADR-0001, ADR-0013): un `user` corre acotado
    a su empresa (`app.company_id`); un `tenant_admin` corre en contexto de asesoría (sin
    `company_id`, ve todo el tenant). El nivel de empresa se resuelve **por petición** (no en el
    token).
    """
    authorization = request.headers.get("authorization", "")
    scheme, _, raw_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not raw_token.strip():
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        claims = decode_access_token(raw_token.strip(), secret=get_settings().jwt_secret)
    except InvalidAccessToken as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc

    resolved: ResolvedTenant | None = getattr(request.state, "tenant", None)
    if resolved is None:
        # El subdominio no resuelve a un tenant activo (inexistente o suspendido): sin contexto, la
        # sesión no puede cablearse a ningún tenant y el token deja de valer (C23).
        raise HTTPException(status_code=401, detail="Not authenticated")
    if claims.tenant_id is None or str(resolved.id) != claims.tenant_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    # Nivel de empresa según el rol, por allowlist explícita (denegar por defecto, ADR-0013 / A2):
    # `user` -> contexto de empresa (acotado a su única empresa activa); `tenant_admin` -> contexto
    # de asesoría (sin acotar). Cualquier otro rol NO recibe visibilidad amplia por defecto: se
    # deniega (403). Un `user` SIEMPRE necesita exactamente una empresa activa: 0 o >1 no fijan un
    # contexto único -> 403, sin servir datos (invariante 1-A estricta), con independencia de si la
    # asesoría tiene otras empresas.
    try:
        scope = scope_for_role(claims.role)
    except RoleNotAuthorized as exc:
        raise HTTPException(status_code=403, detail="Forbidden") from exc

    company: CompanyRef | None = None
    if scope is RlsScope.COMPANY:
        try:
            company = await resolve_user_company(resolved.id, claims.sub)
        except MisconfiguredUserCompany as exc:
            raise HTTPException(status_code=403, detail="Forbidden") from exc

    company_id = company.id if company is not None else None
    async with tenant_session(resolved.id, company_id) as db_session:
        yield AuthContext(
            user_id=UUID(claims.sub),
            tenant_id=resolved.id,
            role=claims.role,
            tenant_slug=resolved.slug,
            session=db_session,
            company=company,
        )

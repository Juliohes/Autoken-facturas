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

from identity.tokens import InvalidAccessToken, decode_access_token
from shared.config import get_settings
from shared.db import tenant_session
from tenancy.resolution import ResolvedTenant


@dataclass(frozen=True)
class AuthContext:
    """Identidad validada de la petición + la sesión de BD abierta en su contexto de tenant."""

    user_id: UUID
    tenant_id: UUID
    role: str
    tenant_slug: str
    session: AsyncSession


async def current_identity(request: Request) -> AsyncIterator[AuthContext]:
    """Valida el token, lo casa con el subdominio y cede una sesión dentro de `tenant_session`."""
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

    async with tenant_session(resolved.id) as db_session:
        yield AuthContext(
            user_id=UUID(claims.sub),
            tenant_id=resolved.id,
            role=claims.role,
            tenant_slug=resolved.slug,
            session=db_session,
        )

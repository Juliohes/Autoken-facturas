"""Dependencias de identidad por petición (S1.3/S4.1): validan el JWT y abren el contexto de BD.

Dos caminos, según si la identidad tiene tenant o no:
- `current_identity` (regla dura del sprint: el **token identifica**, el **subdominio aísla**):
  exige que el `tenant_id` del token case con el tenant del subdominio (S1.2) y abre
  `tenant_session` para que la petición corra dentro de la RLS del tenant.
  - sin cabecera `Authorization` o con firma/formato inválidos -> **401**;
  - el subdominio no resuelve a un tenant activo (p. ej. suspendido) -> **401** (sin contexto);
  - el `tenant_id` del token no casa con el tenant del subdominio -> **403** (otra asesoría).
- `current_platform_identity` (S4.1): un `platform_admin` no tiene tenant, así que no hay nada que
  casar con el subdominio; la barrera es solo el rol del token, con una sesión sin RLS de tenant.

Ambas comparten la lectura/decodificación del token (`_decode_bearer_claims`), único sitio donde
cambia el formato del error 401 de autenticación.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from identity.repository import CompanyRef, MisconfiguredUserCompany, resolve_user_company
from identity.scoping import RlsScope, RoleNotAuthorized, scope_for_role
from identity.tokens import AccessClaims, InvalidAccessToken, decode_access_token
from shared.config import get_settings
from shared.db import platform_session, tenant_session
from tenancy.constants import Role
from tenancy.resolution import ResolvedTenant


def _decode_bearer_claims(request: Request) -> AccessClaims:
    """Lee `Authorization: Bearer <token>` y devuelve sus claims, o 401 (sin cabecera/inválido).

    Compartido por `current_identity` y `current_platform_identity`: mismo criterio de qué cuenta
    como "no autenticado" para ambos caminos, un solo sitio que sincronizar si cambia.
    """
    authorization = request.headers.get("authorization", "")
    scheme, _, raw_token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not raw_token.strip():
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return decode_access_token(raw_token.strip(), secret=get_settings().jwt_secret)
    except InvalidAccessToken as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


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


async def current_identity(request: Request) -> AsyncGenerator[AuthContext, None]:
    """Valida el token, lo casa con el subdominio y cede una sesión dentro de `tenant_session`.

    Tipado como `AsyncGenerator` (no `AsyncIterator`) a propósito: `current_identity_for_me` lo
    envuelve en `contextlib.aclosing`, que exige un `aclose()` explícito en el tipo.

    Según el rol, fija el nivel de empresa de la RLS (ADR-0001, ADR-0013): un `user` corre acotado
    a su empresa (`app.company_id`); un `tenant_admin` corre en contexto de asesoría (sin
    `company_id`, ve todo el tenant). El nivel de empresa se resuelve **por petición** (no en el
    token).
    """
    claims = _decode_bearer_claims(request)

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


@dataclass(frozen=True)
class PlatformAuthContext:
    """Identidad validada de un `platform_admin` + una sesión SIN contexto de tenant (S4.1).

    Distinta de `AuthContext` a propósito: un `platform_admin` no tiene `tenant_id`/empresa (S1.3),
    así que no hay nada que fijar con `SET LOCAL`. Las operaciones de plataforma pasan por funciones
    `SECURITY DEFINER` acotadas (`create_tenant`/`list_tenants`, migración 0010), no por la RLS de
    un tenant.
    """

    user_id: UUID
    session: AsyncSession


async def current_platform_identity(request: Request) -> AsyncIterator[PlatformAuthContext]:
    """Valida el token y exige `role = platform_admin`. Sin contexto de tenant (S4.1).

    A diferencia de `current_identity`, NO depende de que el subdominio resuelva a un tenant (un
    `platform_admin` no pertenece a ninguno): la barrera real es el rol del token firmado, no el
    host por el que llega la petición. Sin cabecera/token válido -> 401; token de otro rol -> 403.
    """
    claims = _decode_bearer_claims(request)

    if claims.role != Role.PLATFORM_ADMIN.value:
        raise HTTPException(status_code=403, detail="Forbidden")

    async with platform_session() as db_session:
        yield PlatformAuthContext(user_id=UUID(claims.sub), session=db_session)


@dataclass(frozen=True)
class MeIdentity:
    """Identidad mínima para `GET /auth/me` (hotfix S4.10): admite tanto un usuario de tenant como
    un `platform_admin` (sin tenant), a diferencia de `AuthContext` (que exige `tenant_id`/
    `tenant_slug` no nulos) y de `PlatformAuthContext` (que no sirve para el camino de tenant).
    """

    user_id: UUID
    session: AsyncSession
    tenant_slug: str | None
    company: CompanyRef | None


async def current_identity_for_me(request: Request) -> AsyncIterator[MeIdentity]:
    """Como `current_identity`, pero también deja pasar a un `platform_admin` sin tenant.

    Antes de este hotfix, `/auth/me` solo pasaba por `current_identity`: un `platform_admin` (que
    entra por `panel`, sin subdominio de tenant que resolver) recibía siempre 401 al llamarlo — una
    regresión real desde que S4.9 (app-shell) empezó a llamar `/auth/me` también tras el login de
    plataforma, no detectada porque los tests de frontend mockean el cliente API.
    """
    claims = _decode_bearer_claims(request)

    if claims.role == Role.PLATFORM_ADMIN.value:
        async with platform_session() as db_session:
            yield MeIdentity(
                user_id=UUID(claims.sub), session=db_session, tenant_slug=None, company=None
            )
        return

    # `contextlib.aclosing` (no un `async for` desnudo, hallazgo de auditoría): FastAPI cierra esta
    # dependencia con `agen.aclose()` en el camino de excepción (p. ej. un fallo de BD ya dentro del
    # handler de `/me`), lanzando `GeneratorExit` en el punto donde está suspendida — un `async for`
    # normal no propaga ese cierre al generador interno (`current_identity`), dejando su `async with
    # tenant_session(...)` (transacción real) sin cerrar de forma determinista.
    async with contextlib.aclosing(current_identity(request)) as identities:
        async for ctx in identities:
            yield MeIdentity(
                user_id=ctx.user_id,
                session=ctx.session,
                tenant_slug=ctx.tenant_slug,
                company=ctx.company,
            )

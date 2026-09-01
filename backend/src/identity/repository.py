"""Acceso a datos del contexto `identity`: el SQL crudo de `users` vive aquí, no en el router.

El router HTTP no conoce el esquema de `users`: pide entidades tipadas a este repositorio. El
repositorio es también el único que decide el camino de lectura según el host:
- en un host de tenant se lee bajo `tenant_session` (RLS del tenant);
- en `panel` (sin tenant) se usa `find_platform_admin` (SECURITY DEFINER), el único camino a un
  `platform_admin` sin tenant.

Las escrituras de la activación pasan por las funciones acotadas `activation_set_password` /
`activation_enroll_totp` (SECURITY DEFINER), gobernadas por el token de activación de un solo uso.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from companies.service import tenant_encryption_key as company_encryption_key
from shared.config import get_settings
from shared.db import platform_session, tenant_session, tenant_statement_session
from shared.db import session as db_session
from tenancy.resolution import ResolvedTenant

# Columnas del usuario necesarias para autenticar. Una sola definición (sin duplicar entre login y
# `find_platform_admin`), para que el esquema quede en un único sitio.
_AUTH_COLUMNS = "id, role, status, password_hash, totp_secret, legacy_bcrypt_hash"


@dataclass(frozen=True)
class AuthUser:
    """Usuario cargado para autenticar. Tipo de dominio (no `dict`) que cruza repo -> servicio."""

    id: str
    tenant_id: str | None
    role: str
    status: str
    password_hash: str | None
    totp_secret: str | None
    # Migración perezosa bcrypt -> Argon2id (migración 0022, cuentas reales importadas de Setex):
    # `None` en cuanto el usuario complete su primer login (ver `identity.service.authenticate`).
    legacy_bcrypt_hash: str | None


@dataclass(frozen=True)
class IdentityRow:
    """Datos públicos de identidad de una fila de `users` (para `/auth/me` y la activación).

    `is_admin_tech` (S4.10) solo tiene sentido real para un `platform_admin`; para un usuario de
    tenant siempre es `False` (ni la consulta de `read_identity` lo selecciona ni el flag existiría
    ahí de otra forma — un `tenant_admin`/`user` nunca pasa el CHECK de negocio de la columna).
    """

    id: str
    email: str
    role: str
    is_admin_tech: bool = False


@dataclass(frozen=True)
class CompanyRef:
    """Referencia mínima a una empresa (id + nombre) para el contexto de un `user`."""

    id: UUID
    name: str


async def load_for_login(
    resolved: ResolvedTenant | None, email: str, *, platform_login: bool
) -> AuthUser | None:
    """Localiza al usuario por email: en el tenant del subdominio, o el platform_admin en panel.

    `platform_login` (host de plataforma, S1.6 C8) habilita el camino a `platform_admin`. En un host
    no-tenant que no sea `panel` no hay contexto ni platform: no hay usuario que cargar (login 401).
    """
    if resolved is not None:
        async with tenant_session(resolved.id) as sess:
            row = (
                await sess.execute(
                    text(f"SELECT {_AUTH_COLUMNS} FROM users WHERE email = :email"),
                    {"email": email},
                )
            ).first()
        tenant_id: str | None = str(resolved.id)
    elif platform_login:
        async with db_session() as sess:
            row = (
                await sess.execute(
                    text(f"SELECT {_AUTH_COLUMNS} FROM find_platform_admin(:email)"),
                    {"email": email},
                )
            ).first()
        tenant_id = None
    else:
        return None
    if row is None:
        return None
    return AuthUser(
        id=str(row.id),
        tenant_id=tenant_id,
        role=row.role,
        status=row.status,
        password_hash=row.password_hash,
        totp_secret=row.totp_secret,
        legacy_bcrypt_hash=row.legacy_bcrypt_hash,
    )


async def migrate_legacy_password(
    resolved: ResolvedTenant | None, *, platform_login: bool, user_id: str, new_password_hash: str
) -> None:
    """Persiste el Argon2id recién generado y borra el bcrypt heredado (migración perezosa, 0022).

    Se abre una sesión nueva y acotada (mismo criterio que el resto de escrituras de este módulo):
    la de `load_for_login` ya se cerró antes de que el servicio decida si migrar. El mismo camino de
    contexto que la lectura (`tenant_session`/`db_session`, según `platform_login`) para respetar la
    RLS: un `platform_admin` vive fuera de cualquier tenant.
    """
    if resolved is not None:
        async with tenant_session(resolved.id) as sess:
            await sess.execute(
                text(
                    "UPDATE users SET password_hash = :hash, legacy_bcrypt_hash = NULL "
                    "WHERE id = :uid"
                ),
                {"hash": new_password_hash, "uid": user_id},
            )
            await sess.commit()
    elif platform_login:
        # La RLS de `users` nunca deja pasar una fila con `tenant_id IS NULL` desde una sesión sin
        # tenant (ni siquiera para UPDATE) — mismo motivo por el que `load_for_login` lee un
        # `platform_admin` vía `find_platform_admin` (SECURITY DEFINER) en vez de un SELECT directo.
        async with db_session() as sess:
            await sess.execute(
                text("SELECT migrate_platform_admin_password(:uid, :hash)"),
                {"uid": user_id, "hash": new_password_hash},
            )
            await sess.commit()


def _identity_row(row: object | None) -> IdentityRow | None:
    """Mapea la fila cruda a `IdentityRow`, compartido por `read_identity`/`read_platform_identity`
    (hallazgo de auditoría: el mapeo estaba duplicado literalmente). `is_admin_tech` con
    `getattr(..., False)`: solo la consulta de `read_platform_identity` selecciona esa columna."""
    if row is None:
        return None
    return IdentityRow(
        id=str(row.id),  # type: ignore[attr-defined]
        email=row.email,  # type: ignore[attr-defined]
        role=row.role,  # type: ignore[attr-defined]
        is_admin_tech=getattr(row, "is_admin_tech", False),
    )


async def read_identity(session: AsyncSession, user_id: str) -> IdentityRow | None:
    """Lee la identidad pública de un usuario dentro de la sesión ya abierta (RLS del tenant)."""
    row = (
        await session.execute(
            text("SELECT id, email, role FROM users WHERE id = :id"),
            {"id": user_id},
        )
    ).first()
    return _identity_row(row)


async def read_platform_identity(session: AsyncSession, user_id: str) -> IdentityRow | None:
    """Lee la identidad pública de un `platform_admin` por id (hotfix S4.10, migración 0016).

    Camino equivalente a `read_identity`, pero para una sesión sin contexto de tenant
    (`platform_session`): la RLS bloquea el `SELECT` directo sobre `users` igual que siempre, así
    que se salta por la misma función `SECURITY DEFINER` que ya usa el login por email.
    """
    row = (
        await session.execute(
            text("SELECT id, email, role, is_admin_tech FROM find_platform_admin_by_id(:id)"),
            {"id": user_id},
        )
    ).first()
    return _identity_row(row)


class MisconfiguredUserCompany(Exception):
    """El `user` no resuelve a un contexto de empresa único: 0 o >1 empresas activas (1-A)."""


async def resolve_user_company(tenant_id: UUID, user_id: str) -> CompanyRef:
    """Empresa activa única de un `user` para su contexto de empresa (invariante 1-A estricta).

    Se lee en **contexto de asesoría** (`app.company_id` sin fijar): así se ven todas las
    memberships del tenant para contar cuántas empresas activas tiene el usuario.

    En el mundo real un empleado nace con su empresa (S1.4); tener **exactamente una** empresa
    activa es la única configuración válida, con independencia de si la asesoría tiene otras
    empresas:

    - Exactamente una empresa activa -> se devuelve (contexto de empresa).
    - 0 o >1 -> cuenta mal configurada (`MisconfiguredUserCompany`); el llamante responde 403 sin
      servir datos (nunca un contexto ambiguo).
    """
    encryption_key = company_encryption_key(get_settings(), tenant_id)
    async with tenant_session(tenant_id) as sess:
        rows = (
            await sess.execute(
                text(
                    "SELECT c.id, pgp_sym_decrypt(c.name, :key)::text AS name FROM memberships m "
                    "JOIN companies c ON c.id = m.company_id "
                    "WHERE m.user_id = :uid AND c.status = 'active'"
                ),
                {"uid": user_id, "key": encryption_key},
            )
        ).all()
    if len(rows) != 1:
        raise MisconfiguredUserCompany
    row = rows[0]
    return CompanyRef(id=row.id, name=row.name)


async def resolve_user_company_id(tenant_id: UUID, user_id: str) -> UUID:
    """Resuelve solo el id de empresa para dependencias que no necesitan el nombre descifrado."""
    async with tenant_statement_session() as sess:
        rows = (
            await sess.execute(
                text(
                    "SELECT id FROM public.resolve_user_company_id_for_app(:tid, :uid)"
                ),
                {"tid": str(tenant_id), "uid": user_id},
            )
        ).all()
    if len(rows) != 1:
        raise MisconfiguredUserCompany
    return UUID(str(rows[0].id))


async def find_platform_admin_for_reissue(email: str) -> tuple[str, bool] | None:
    """(user_id, ya_activada) de un `platform_admin` por email, o `None` si no existe.

    Reutiliza `find_platform_admin` (SECURITY DEFINER, S1.3, el mismo camino del login) para que
    `scripts/create_account.py reissue-activation` pueda reemitir un token de activación perdido sin
    tocar la contraseña: si `password_hash` ya está fijado, la cuenta completó su activación y esto
    ya no es un token perdido sino una contraseña olvidada (flujo distinto, no construido aquí).
    """
    async with db_session() as sess:
        row = (
            await sess.execute(
                text("SELECT id, password_hash FROM find_platform_admin(:email)"),
                {"email": email},
            )
        ).first()
    if row is None:
        return None
    return str(row.id), row.password_hash is not None


async def set_activation_password(user_id: str, password_hash: str) -> IdentityRow | None:
    """Fija la contraseña SOLO si la cuenta es activable (activa y sin contraseña); `None` si no.

    El guard `status = 'active' AND password_hash IS NULL` está en la función SQL (atómico): una
    cuenta pendiente de aprobación (S1.4) o ya activada no es activable y devuelve 0 filas.
    """
    async with db_session() as sess:
        row = (
            await sess.execute(
                text("SELECT id, email, role FROM activation_set_password(:uid, :hash)"),
                {"uid": user_id, "hash": password_hash},
            )
        ).first()
        await sess.commit()
    if row is None:
        return None
    return IdentityRow(id=str(row.id), email=row.email, role=row.role)


async def enroll_totp(user_id: str, secret: str) -> None:
    """Enrola el secreto TOTP al confirmar la activación (guard `totp_secret IS NULL`, F3)."""
    async with db_session() as sess:
        await sess.execute(
            text("SELECT activation_enroll_totp(:uid, :secret)"),
            {"uid": user_id, "secret": secret},
        )
        await sess.commit()


async def create_platform_admin_account(email: str, *, is_admin_tech: bool = False) -> IdentityRow:
    """Da de alta un `platform_admin` sembrado (migración 0023), pendiente de activación.

    Vía `provision_platform_admin` (SECURITY DEFINER): único camino legítimo, nunca una conexión de
    superusuario embebida en código de aplicación. Email duplicado -> `IntegrityError` (índice único
    parcial de 0003), sin capturar aquí: la decide el llamante (CLI de `scripts/create_account.py`).
    """
    async with platform_session() as sess:
        row = (
            await sess.execute(
                text(
                    "SELECT id, email, role, is_admin_tech "
                    "FROM provision_platform_admin(:email, :is_admin_tech)"
                ),
                {"email": email, "is_admin_tech": is_admin_tech},
            )
        ).one()
    return IdentityRow(
        id=str(row.id), email=row.email, role=row.role, is_admin_tech=row.is_admin_tech
    )


async def create_tenant_account(tenant_id: str, email: str, role: str) -> IdentityRow:
    """Da de alta un `tenant_admin`/`user` sembrado directamente (sin el registro+aprobación de
    S1.4), pendiente de activación. Vía `provision_tenant_account` (SECURITY DEFINER, migración
    0023); `role='platform_admin'` lo rechaza la propia función SQL."""
    async with platform_session() as sess:
        row = (
            await sess.execute(
                text("SELECT id, email, role FROM provision_tenant_account(:tid, :email, :role)"),
                {"tid": tenant_id, "email": email, "role": role},
            )
        ).one()
    return IdentityRow(id=str(row.id), email=row.email, role=row.role)


async def revoke_platform_admin_account(email: str) -> str | None:
    """Da de baja (DELETE) un `platform_admin` existente; `None` si no había ninguno con ese email.

    Vía `revoke_platform_admin` (SECURITY DEFINER, migración 0023). Deliberadamente NO reasigna la
    fila a un tenant (evitaría arrastrar `password_hash`/`totp_secret` ya fijados de la cuenta de
    plataforma) — dar de alta la cuenta de tenant nueva es un paso aparte, `create_tenant_account`.
    """
    async with platform_session() as sess:
        row = (
            await sess.execute(
                text("SELECT id FROM revoke_platform_admin(:email)"),
                {"email": email},
            )
        ).first()
    return str(row.id) if row is not None else None


async def reset_account_password(email: str, tenant_id: str | None) -> str | None:
    """Borra `password_hash`/`totp_secret`/`legacy_bcrypt_hash` de una cuenta ya activada; `None`
    si no había ninguna cuenta activada con ese email en ese ámbito (`tenant_id=None` = plataforma).

    Vía `reset_account_password` (SECURITY DEFINER, migración 0024): deja la cuenta en el estado
    "recién sembrada" para que un nuevo `issue_activation_token` + `POST /auth/activate` permita
    fijar una contraseña nueva desde cero, sin que esta pase nunca por el operador.
    """
    async with platform_session() as sess:
        row = (
            await sess.execute(
                text("SELECT id FROM reset_account_password(:email, :tenant_id)"),
                {"email": email, "tenant_id": tenant_id},
            )
        ).first()
    return str(row.id) if row is not None else None

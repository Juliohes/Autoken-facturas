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

from shared.db import session as db_session
from shared.db import tenant_session
from tenancy.resolution import ResolvedTenant

# Columnas del usuario necesarias para autenticar. Una sola definición (sin duplicar entre login y
# `find_platform_admin`), para que el esquema quede en un único sitio.
_AUTH_COLUMNS = "id, role, status, password_hash, totp_secret"


@dataclass(frozen=True)
class AuthUser:
    """Usuario cargado para autenticar. Tipo de dominio (no `dict`) que cruza repo -> servicio."""

    id: str
    tenant_id: str | None
    role: str
    status: str
    password_hash: str | None
    totp_secret: str | None


@dataclass(frozen=True)
class IdentityRow:
    """Datos públicos de identidad de una fila de `users` (para `/auth/me` y la activación)."""

    id: str
    email: str
    role: str


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
    )


def _identity_row(row: object | None) -> IdentityRow | None:
    """Mapea la fila cruda (`id, email, role`) a `IdentityRow`, compartido por `read_identity`/
    `read_platform_identity` (hallazgo de auditoría: el mapeo estaba duplicado literalmente)."""
    if row is None:
        return None
    return IdentityRow(id=str(row.id), email=row.email, role=row.role)  # type: ignore[attr-defined]


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
            text("SELECT id, email, role FROM find_platform_admin_by_id(:id)"),
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
    async with tenant_session(tenant_id) as sess:
        rows = (
            await sess.execute(
                text(
                    "SELECT c.id, c.name FROM memberships m "
                    "JOIN companies c ON c.id = m.company_id "
                    "WHERE m.user_id = :uid AND c.status = 'active'"
                ),
                {"uid": user_id},
            )
        ).all()
    if len(rows) != 1:
        raise MisconfiguredUserCompany
    row = rows[0]
    return CompanyRef(id=row.id, name=row.name)


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

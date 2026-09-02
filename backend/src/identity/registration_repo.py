"""Acceso a datos del registro con aprobación (S1.4): el SQL de `users`/`memberships` del alta.

La sesión llega abierta en el contexto de tenant (RLS): en el registro público, el contexto de
asesoría abierto desde el subdominio (`public_tenant_context`); en la gestión, el del `tenant_admin`
(`current_identity`). El `tenant_id` de las escrituras NO viaja por parámetro: se deriva del
contexto (`app.tenant_id`), la misma fuente que la RLS, de modo que ninguna fila puede crearse fuera
del tenant de la petición. Las empresas del registro se gestionan por el repositorio de `companies`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tenancy.constants import CompanyStatus, Role, UserStatus

# `tenant_id` de las escrituras derivado del contexto de la sesión (coherente con la RLS).
_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


@dataclass(frozen=True)
class PendingRegistration:
    """Un registro pendiente para el listado del admin: usuario + empresa asociada.

    `joins_existing_company` señala que el CIF del registro coincidía con una empresa **ya activa**
    de la asesoría (el usuario se une a ella, regla 1-A), no un alta de empresa nueva: la pantalla
    de aprobación puede marcar "se une a una empresa ya existente" (defensa ante secuestro por CIF).
    `email_verified` (bloque 2, PROMPT-AUTOFACTU-AUTH-COMPLETO): informa, no bloquea -- un admin
    puede aprobar igual un registro con el email todavía sin confirmar.
    """

    id: UUID
    email: str
    company: str | None
    joins_existing_company: bool
    email_verified: bool


@dataclass(frozen=True)
class RegisteredUser:
    """Estado mínimo de un usuario del flujo de registro (para aprobar/rechazar)."""

    id: UUID
    status: str


@dataclass(frozen=True)
class LinkedCompany:
    """Empresa vinculada a un usuario (id + estado), para decidir el borrado al rechazar."""

    id: UUID
    status: str


async def email_exists(session: AsyncSession, email: str) -> bool:
    """True si el email ya existe en el tenant del contexto (unicidad `(tenant_id, email)`)."""
    row = (
        await session.execute(
            text("SELECT 1 FROM users WHERE email = :email LIMIT 1"),
            {"email": email},
        )
    ).first()
    return row is not None


async def insert_pending_user(session: AsyncSession, *, email: str, password_hash: str) -> UUID:
    """Crea el usuario pendiente (`role=user`, `status=pending`) con su hash y devuelve su id."""
    row = (
        await session.execute(
            text(
                f"INSERT INTO users (tenant_id, email, role, status, password_hash) "
                f"VALUES ({_TENANT_FROM_CONTEXT}, :email, :role, :status, :hash) RETURNING id"
            ),
            {
                "email": email,
                "role": Role.USER.value,
                "status": UserStatus.PENDING.value,
                "hash": password_hash,
            },
        )
    ).one()
    return cast(UUID, row.id)


async def insert_membership(session: AsyncSession, *, user_id: UUID, company_id: UUID) -> None:
    """Vincula el usuario a su empresa (membership) en el tenant del contexto (regla 1-A)."""
    await session.execute(
        text(
            f"INSERT INTO memberships (user_id, company_id, tenant_id) "
            f"VALUES (:uid, :cid, {_TENANT_FROM_CONTEXT})"
        ),
        {"uid": str(user_id), "cid": str(company_id)},
    )


async def tenant_admin_emails(session: AsyncSession) -> list[str]:
    """Emails de los `tenant_admin` activos de la asesoría (a quienes se avisa del registro)."""
    rows = (
        await session.execute(
            text("SELECT email FROM users WHERE role = :role AND status = :active"),
            {"role": Role.TENANT_ADMIN.value, "active": UserStatus.ACTIVE.value},
        )
    ).all()
    return [r.email for r in rows]


async def list_pending(session: AsyncSession, *, encryption_key: str) -> list[PendingRegistration]:
    """Lista los registros pendientes de la asesoría (usuario + empresa), por antigüedad.

    Trae también el estado de la empresa vinculada: si es `active`, el registro se une a una empresa
    ya existente (regla 1-A) y no crea una nueva, señal para la pantalla de aprobación (M2).

    `companies.name` vive cifrado desde S5.2: se descifra aquí con la clave del tenant del contexto.
    """
    rows = (
        await session.execute(
            text(
                "SELECT u.id, u.email, u.email_verified_at, "
                " pgp_sym_decrypt(c.name, :key)::text AS company, c.status AS company_status "
                "FROM users u "
                "LEFT JOIN memberships m ON m.user_id = u.id "
                "LEFT JOIN companies c ON c.id = m.company_id "
                "WHERE u.status = :pending AND u.role = :role "
                "ORDER BY u.created_at"
            ),
            {"pending": UserStatus.PENDING.value, "role": Role.USER.value, "key": encryption_key},
        )
    ).all()
    return [
        PendingRegistration(
            id=r.id,
            email=r.email,
            company=r.company,
            joins_existing_company=r.company_status == CompanyStatus.ACTIVE.value,
            email_verified=r.email_verified_at is not None,
        )
        for r in rows
    ]


async def mark_email_verified(session: AsyncSession, user_id: UUID) -> None:
    """Marca el email del registrante como verificado (bloque 2). No-op si el usuario no existe en
    el contexto (RLS): un token de otro tenant ya se descarta antes de llegar aquí (F2)."""
    await session.execute(
        text("UPDATE users SET email_verified_at = now() WHERE id = :id"),
        {"id": str(user_id)},
    )


async def get_user(session: AsyncSession, user_id: UUID) -> RegisteredUser | None:
    """Lee el estado de un usuario por id en el contexto (RLS oculta los de otro tenant -> None)."""
    row = (
        await session.execute(
            text("SELECT id, status FROM users WHERE id = :id"),
            {"id": str(user_id)},
        )
    ).first()
    if row is None:
        return None
    return RegisteredUser(id=row.id, status=row.status)


async def activate_user(session: AsyncSession, user_id: UUID) -> None:
    """Pasa el usuario a `active` (la aprobación del admin es la puerta de login, 2-B)."""
    await session.execute(
        text("UPDATE users SET status = :active WHERE id = :id"),
        {"active": UserStatus.ACTIVE.value, "id": str(user_id)},
    )


async def linked_companies(session: AsyncSession, user_id: UUID) -> list[LinkedCompany]:
    """Empresas vinculadas al usuario (id + estado), para decidir el borrado al rechazar."""
    rows = (
        await session.execute(
            text(
                "SELECT c.id, c.status FROM memberships m "
                "JOIN companies c ON c.id = m.company_id "
                "WHERE m.user_id = :uid"
            ),
            {"uid": str(user_id)},
        )
    ).all()
    return [LinkedCompany(id=r.id, status=r.status) for r in rows]


async def delete_user(session: AsyncSession, user_id: UUID) -> None:
    """Borra el usuario pendiente (sus memberships caen en cascada). Rechazo del registro (C9)."""
    await session.execute(text("DELETE FROM users WHERE id = :id"), {"id": str(user_id)})

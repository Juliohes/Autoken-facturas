"""Acceso a datos de "olvidé mi contraseña": la búsqueda por email vive aquí, no en el dominio.

La sesión llega abierta en el contexto de tenant del subdominio (`public_tenant_context`, igual que
el registro público): la RLS ya acota la búsqueda al tenant de la petición, así que no hace falta
ningún parámetro `tenant_id` explícito en el SQL (mismo criterio que
`registration_repo.email_exists`).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tenancy.constants import UserStatus


@dataclass(frozen=True)
class ResettableUser:
    """Un usuario en condiciones de restablecer su contraseña (activo, con contraseña ya fijada)."""

    id: UUID


async def find_resettable_user(session: AsyncSession, email: str) -> ResettableUser | None:
    """Busca por email en el tenant del contexto un usuario activo y con contraseña ya fijada.

    `None` tanto si el email no existe como si existe pero no es restablecible (pendiente de
    aprobación, o activo sin contraseña todavía): el llamante no debe distinguir el motivo
    (anti-enumeración, igual que `registration.register`).
    """
    row = (
        await session.execute(
            text(
                "SELECT id FROM users "
                "WHERE email = :email AND status = :active AND password_hash IS NOT NULL"
            ),
            {"email": email, "active": UserStatus.ACTIVE.value},
        )
    ).first()
    if row is None:
        return None
    return ResettableUser(id=row.id)

"""Acceso a datos de `tenancy` distinto de la resolución de subdominio (S4.2): lectura de
`tenant_branding` para el tenant ya resuelto. A diferencia de `tenants` (aislada por su propio `id`,
caso especial que necesita `SECURITY DEFINER`, ver `resolution.py`), `tenant_branding` tiene RLS
normal por `tenant_id` y el rol runtime ya tiene `SELECT` sobre ella (grant genérico de tablas de
tenant, migración 0001): una `tenant_session` corriente basta, sin función acotada nueva.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TenantBranding:
    """Identidad visual de un tenant (S4.1/S4.2). Cada campo puede ser `None` (sin branding)."""

    logo_url: str | None
    color_primary: str | None
    color_secondary: str | None
    app_name: str | None
    favicon: str | None


async def get_branding(session: AsyncSession, tenant_id: UUID) -> TenantBranding | None:
    """Branding del tenant del contexto, o `None` si no tiene fila en `tenant_branding`.

    `None` es un caso legítimo (S4.2 spec caso límite): un tenant sin branding configurado. El
    llamante decide los valores por defecto ("Setex tal cual hoy" vive en el frontend, no aquí).
    """
    row = (
        await session.execute(
            text(
                "SELECT logo_url, color_primary, color_secondary, app_name, favicon "
                "FROM tenant_branding WHERE tenant_id = :tenant_id"
            ),
            {"tenant_id": str(tenant_id)},
        )
    ).first()
    if row is None:
        return None
    return TenantBranding(
        logo_url=row.logo_url,
        color_primary=row.color_primary,
        color_secondary=row.color_secondary,
        app_name=row.app_name,
        favicon=row.favicon,
    )

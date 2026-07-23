"""Acceso a datos del alta/listado de tenants (S4.1): llama a las funciones `SECURITY DEFINER`
`create_tenant`/`list_tenants` (migración 0010), único camino permitido para tocar `tenants`/
`tenant_branding` sin contexto de tenant. Ningún SQL directo sobre esas tablas desde aquí.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TenantRecord:
    """Un tenant tal como lo devuelven `create_tenant`/`list_tenants` (sin datos de branding)."""

    id: UUID
    slug: str
    name: str
    status: str
    is_demo: bool
    created_at: datetime


async def create_tenant(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    logo_url: str | None,
    color_primary: str | None,
    color_secondary: str | None,
) -> TenantRecord:
    """Crea el tenant + su branding en una única llamada atómica (o las dos filas, o ninguna).

    `app_name` no se pide aquí: la función SQL lo rellena con `name` si no se especifica (spec S4.1
    §0 decisión 3); este repositorio no tiene opinión sobre ese default, solo pasa `NULL`.
    """
    row = (
        await session.execute(
            text(
                "SELECT id, slug, name, status, is_demo, created_at "
                "FROM create_tenant(:slug, :name, :logo_url, :color_primary, :color_secondary, "
                "NULL)"
            ),
            {
                "slug": slug,
                "name": name,
                "logo_url": logo_url,
                "color_primary": color_primary,
                "color_secondary": color_secondary,
            },
        )
    ).one()
    return TenantRecord(
        id=row.id,
        slug=row.slug,
        name=row.name,
        status=row.status,
        is_demo=row.is_demo,
        created_at=row.created_at,
    )


async def list_tenants(session: AsyncSession) -> list[TenantRecord]:
    """Todos los tenants, más reciente primero (spec S4.1 §3 C7)."""
    rows = (
        await session.execute(
            text("SELECT id, slug, name, status, is_demo, created_at FROM list_tenants()")
        )
    ).all()
    return [
        TenantRecord(
            id=row.id,
            slug=row.slug,
            name=row.name,
            status=row.status,
            is_demo=row.is_demo,
            created_at=row.created_at,
        )
        for row in rows
    ]

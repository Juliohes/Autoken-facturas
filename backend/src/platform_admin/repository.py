"""Acceso a datos del alta/listado de tenants (S4.1): llama a las funciones `SECURITY DEFINER`
`create_tenant`/`list_tenants` (migración 0010), único camino permitido para tocar `tenants`/
`tenant_branding` sin contexto de tenant. Ningún SQL directo sobre esas tablas desde aquí.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
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


@dataclass(frozen=True)
class PurgeOutcome:
    """Resultado de `purge_demo_tenant` (S4.4): distingue "no existía" de "existía pero no era
    demo" sin un pre-chequeo aparte en Python (spec §0 decisión 3, ver migración 0011)."""

    existed: bool
    was_demo: bool


def _to_tenant_record(row: Any) -> TenantRecord:
    return TenantRecord(
        id=row.id,
        slug=row.slug,
        name=row.name,
        status=row.status,
        is_demo=row.is_demo,
        created_at=row.created_at,
    )


async def create_tenant(
    session: AsyncSession,
    *,
    slug: str,
    name: str,
    logo_url: str | None,
    color_primary: str | None,
    color_secondary: str | None,
    is_demo: bool = False,
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
                "NULL, :is_demo)"
            ),
            {
                "slug": slug,
                "name": name,
                "logo_url": logo_url,
                "color_primary": color_primary,
                "color_secondary": color_secondary,
                "is_demo": is_demo,
            },
        )
    ).one()
    return _to_tenant_record(row)


async def list_tenants(session: AsyncSession) -> list[TenantRecord]:
    """Todos los tenants, más reciente primero (spec S4.1 §3 C7)."""
    rows = (
        await session.execute(
            text("SELECT id, slug, name, status, is_demo, created_at FROM list_tenants()")
        )
    ).all()
    return [_to_tenant_record(row) for row in rows]


async def convert_tenant_to_production(
    session: AsyncSession, tenant_id: UUID
) -> TenantRecord | None:
    """Pone `is_demo=false` (idempotente, S4.4). `None` si el id no existe."""
    row = (
        await session.execute(
            text(
                "SELECT id, slug, name, status, is_demo, created_at "
                "FROM convert_tenant_to_production(:tenant_id)"
            ),
            {"tenant_id": tenant_id},
        )
    ).one_or_none()
    return _to_tenant_record(row) if row is not None else None


async def purge_demo_tenant(session: AsyncSession, tenant_id: UUID) -> PurgeOutcome:
    """Borra el tenant entero si `is_demo=true` (S4.4).

    `SELECT ... FOR UPDATE` dentro de la propia función SQL bloquea la fila hasta el commit: la
    comprobación de "es demo" y el borrado ocurren atómicamente en Postgres, sin round-trip a Python
    de por medio, así que no hay ninguna carrera posible entre "comprobar" y "borrar" (dos purgas o
    una purga y una conversión concurrentes sobre el mismo id se serializan en el `FOR UPDATE`).
    """
    row = (
        await session.execute(
            text("SELECT existed, was_demo FROM purge_demo_tenant(:tenant_id)"),
            {"tenant_id": tenant_id},
        )
    ).one()
    return PurgeOutcome(existed=row.existed, was_demo=row.was_demo)

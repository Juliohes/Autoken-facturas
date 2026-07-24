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

from platform_admin.export import TENANT_TABLES


@dataclass(frozen=True)
class TenantRecord:
    """Un tenant tal como lo devuelven `create_tenant`/`list_tenants` (sin datos de branding).

    `custom_domain` (S4.6) lo rellenan `list_tenants`, `convert_tenant_to_production` (migración
    0014: un tenant demo puede tener ya uno asignado antes de convertirse a producción) y
    `set_tenant_custom_domain`. Solo `create_tenant` lo deja siempre en `None`, porque un tenant
    recién creado nunca tuvo tiempo de que se le asignara uno (spec S4.6 §3 decisión 3).
    """

    id: UUID
    slug: str
    name: str
    status: str
    is_demo: bool
    created_at: datetime
    custom_domain: str | None = None


@dataclass(frozen=True)
class PurgeOutcome:
    """Resultado de `purge_demo_tenant` (S4.4): distingue "no existía" de "existía pero no era
    demo" sin un pre-chequeo aparte en Python (spec §0 decisión 3, ver migración 0011)."""

    existed: bool
    was_demo: bool


@dataclass(frozen=True)
class DeleteOutcome:
    """Resultado de `delete_tenant` (S4.7): distingue cada motivo de fallo sin un pre-chequeo
    aparte en Python (mismo espíritu que `PurgeOutcome`, S4.4; ver migración 0015)."""

    existed: bool
    slug_matched: bool
    exported: bool
    deleted: bool


@dataclass(frozen=True)
class TenantMetrics:
    """Una fila de `platform_tenant_metrics()` (S4.5): consumo agregado de un tenant."""

    tenant_id: UUID
    slug: str
    name: str
    companies_count: int
    active_users_count: int
    invoices_this_month: int
    ocr_extractions_count: int
    last_activity_at: datetime | None


def _to_tenant_record(row: Any) -> TenantRecord:
    return TenantRecord(
        id=row.id,
        slug=row.slug,
        name=row.name,
        status=row.status,
        is_demo=row.is_demo,
        created_at=row.created_at,
        custom_domain=getattr(row, "custom_domain", None),
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
    """Todos los tenants, más reciente primero (spec S4.1 §3 C7); incluye `custom_domain` (S4.6)."""
    rows = (
        await session.execute(
            text(
                "SELECT id, slug, name, status, is_demo, created_at, custom_domain "
                "FROM list_tenants()"
            )
        )
    ).all()
    return [_to_tenant_record(row) for row in rows]


async def convert_tenant_to_production(
    session: AsyncSession, tenant_id: UUID
) -> TenantRecord | None:
    """Pone `is_demo=false` (idempotente, S4.4). `None` si el id no existe.

    Incluye `custom_domain` real (S4.6, migración 0014): un tenant demo puede tener ya uno
    asignado antes de convertirse a producción; devolver siempre `None` ahí sería incorrecto, no
    solo "sin rellenar" (a diferencia de `create_tenant`, donde `None` sí es siempre correcto).
    """
    row = (
        await session.execute(
            text(
                "SELECT id, slug, name, status, is_demo, created_at, custom_domain "
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


async def set_tenant_custom_domain(
    session: AsyncSession, tenant_id: UUID, custom_domain: str | None
) -> TenantRecord | None:
    """Asigna o quita (`None`) el dominio propio de un tenant (S4.6). `None` si el id no existe.

    Duplicado -> `IntegrityError` (constraint `tenants_custom_domain_key`), sin capturar aquí: el
    `service` lo traduce a `DuplicateCustomDomain`, mismo patrón que `create_tenant`/slug (S4.1).
    """
    row = (
        await session.execute(
            text(
                "SELECT id, slug, name, status, is_demo, created_at, custom_domain "
                "FROM set_tenant_custom_domain(:tenant_id, :custom_domain)"
            ),
            {"tenant_id": tenant_id, "custom_domain": custom_domain},
        )
    ).one_or_none()
    return _to_tenant_record(row) if row is not None else None


async def tenant_metrics(session: AsyncSession) -> list[TenantMetrics]:
    """Consumo agregado de todos los tenants, ordenado por slug (spec S4.5 §0 decisión 3)."""
    rows = (
        await session.execute(
            text(
                "SELECT tenant_id, slug, name, companies_count, active_users_count, "
                "invoices_this_month, ocr_extractions_count, last_activity_at "
                "FROM platform_tenant_metrics()"
            )
        )
    ).all()
    return [
        TenantMetrics(
            tenant_id=row.tenant_id,
            slug=row.slug,
            name=row.name,
            companies_count=row.companies_count,
            active_users_count=row.active_users_count,
            invoices_this_month=row.invoices_this_month,
            ocr_extractions_count=row.ocr_extractions_count,
            last_activity_at=row.last_activity_at,
        )
        for row in rows
    ]


async def suspend_tenant(session: AsyncSession, tenant_id: UUID) -> TenantRecord | None:
    """Pone `status='suspended'` (idempotente, S4.7). `None` si el id no existe."""
    row = (
        await session.execute(
            text(
                "SELECT id, slug, name, status, is_demo, created_at, custom_domain "
                "FROM suspend_tenant(:tenant_id)"
            ),
            {"tenant_id": tenant_id},
        )
    ).one_or_none()
    return _to_tenant_record(row) if row is not None else None


async def reactivate_tenant(session: AsyncSession, tenant_id: UUID) -> TenantRecord | None:
    """Pone `status='active'` (idempotente, S4.7). `None` si el id no existe."""
    row = (
        await session.execute(
            text(
                "SELECT id, slug, name, status, is_demo, created_at, custom_domain "
                "FROM reactivate_tenant(:tenant_id)"
            ),
            {"tenant_id": tenant_id},
        )
    ).one_or_none()
    return _to_tenant_record(row) if row is not None else None


async def mark_tenant_exported(session: AsyncSession, tenant_id: UUID) -> datetime | None:
    """Pone `last_export_at=now()` (S4.7). Devuelve el valor nuevo, o `None` si el id no existe."""
    row = (
        await session.execute(
            text("SELECT last_export_at FROM mark_tenant_exported(:tenant_id)"),
            {"tenant_id": tenant_id},
        )
    ).one_or_none()
    return row.last_export_at if row is not None else None


async def delete_tenant(session: AsyncSession, tenant_id: UUID, confirm_slug: str) -> DeleteOutcome:
    """Borra el tenant entero si `confirm_slug` coincide y hubo al menos un export previo (S4.7).

    `SELECT ... FOR UPDATE` dentro de la propia función SQL bloquea la fila hasta el commit: la
    comprobación completa y el borrado ocurren atómicamente en Postgres (mismo patrón que
    `purge_demo_tenant`, S4.4, para no repetir la carrera que esa tarea encontró y corrigió).
    """
    row = (
        await session.execute(
            text(
                "SELECT existed, slug_matched, exported, deleted "
                "FROM delete_tenant(:tenant_id, :confirm_slug)"
            ),
            {"tenant_id": tenant_id, "confirm_slug": confirm_slug},
        )
    ).one()
    return DeleteOutcome(
        existed=row.existed,
        slug_matched=row.slug_matched,
        exported=row.exported,
        deleted=row.deleted,
    )


async def fetch_tenant_table_rows(session: AsyncSession, table: str) -> list[dict[str, Any]]:
    """Todas las filas de `table` visibles en la sesión (S4.7): pensada para llamarse dentro de un
    `tenant_session(tenant_id)` (RLS ya acota a ese tenant, `company_id` sin fijar = toda la
    asesoría) — este repositorio no filtra por `tenant_id` aparte, confía en la RLS ya probada por
    el resto del proyecto (la propia RLS `FORCE` es la frontera de aislamiento real).

    `table` debe ser uno de `platform_admin.export.TENANT_TABLES`: SQL no permite parametrizar un
    nombre de tabla vía bind param (solo valores), así que se valida contra esa lista blanca antes
    de interpolarlo — nunca llega aquí un nombre de tabla que no sea esa constante interna, pero la
    comprobación es defensa en profundidad barata frente a un futuro llamador que se equivoque.
    """
    if table not in TENANT_TABLES:
        raise ValueError(f"Tabla no reconocida para export de tenant: {table!r}")
    rows = (await session.execute(text(f"SELECT * FROM {table}"))).mappings().all()  # noqa: S608
    return [dict(row) for row in rows]

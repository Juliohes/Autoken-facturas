"""Lógica de dominio del alta/listado de tenants (S4.1): validación de slug/color y traducción de
la violación del UNIQUE de `tenants.slug` a un error de dominio. El router es fino; el SQL vive en
`repository` (funciones `SECURITY DEFINER`).
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_intake import service as intake_service
from invoice_intake import storage
from platform_admin import repository
from platform_admin.repository import TenantRecord
from shared.integrity import violates_unique_constraint
from tenancy.constants import RESERVED_SLUGS

# Etiqueta DNS de primer nivel (el slug se usa tal cual como subdominio): minúsculas, dígitos y
# guiones, sin empezar/terminar en guión, 1-63 caracteres. La longitud se valida aquí (no solo se
# delega a la columna, `String(63)`): un slug de formato válido pero más largo violaría la columna
# con un `DataError` de Postgres (500), no el 422 que documenta la spec (S4.1 §3 C3).
_SLUG_FORMAT = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

# `#RRGGBB` o `#RRGGBBAA` (con canal alfa opcional), coherente con `tenant_branding.color_*`
# (String(9): 1 `#` + hasta 8 hex).
_COLOR_FORMAT = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")

_SLUG_UNIQUE_CONSTRAINT = "tenants_slug_key"


class PlatformError(Exception):
    """Raíz de los errores de dominio del panel de plataforma."""


class InvalidSlug(PlatformError):
    """El slug no tiene forma de subdominio válida o es uno reservado de plataforma (-> 422)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class InvalidColor(PlatformError):
    """Un color no es hexadecimal `#RRGGBB`/`#RRGGBBAA` (-> 422)."""


class InvalidName(PlatformError):
    """El nombre está vacío o son solo espacios (-> 422, spec S4.1 §5)."""


class DuplicateSlug(PlatformError):
    """Ya existe un tenant con ese slug (-> 409)."""


class TenantNotFound(PlatformError):
    """No existe ningún tenant con ese id (-> 404, S4.4)."""


class TenantNotDemo(PlatformError):
    """El tenant existe pero no es demo: no se puede purgar por esta vía (-> 409, S4.4)."""


def _validated_name(name: str) -> str:
    if not name.strip():
        raise InvalidName
    return name


def _validated_slug(slug: str) -> str:
    if not _SLUG_FORMAT.match(slug):
        raise InvalidSlug(
            "El slug debe ser minúsculas, dígitos y guiones, sin empezar/terminar en guión"
        )
    if slug in RESERVED_SLUGS:
        raise InvalidSlug("Ese slug está reservado para la plataforma")
    return slug


def _validated_color(color: str | None) -> str | None:
    if color is None:
        return None
    if not _COLOR_FORMAT.match(color):
        raise InvalidColor
    return color


async def create_tenant(
    session: AsyncSession,
    *,
    name: str,
    slug: str,
    logo_url: str | None,
    color_primary: str | None,
    color_secondary: str | None,
    is_demo: bool = False,
) -> TenantRecord:
    """Da de alta un tenant + su branding (S4.1, `is_demo` desde S4.4). Nombre/slug/color inválidos
    -> 422; duplicado -> 409."""
    canonical_name = _validated_name(name)
    canonical_slug = _validated_slug(slug)
    primary = _validated_color(color_primary)
    secondary = _validated_color(color_secondary)
    try:
        return await repository.create_tenant(
            session,
            slug=canonical_slug,
            name=canonical_name,
            logo_url=logo_url,
            color_primary=primary,
            color_secondary=secondary,
            is_demo=is_demo,
        )
    except IntegrityError as exc:
        if violates_unique_constraint(exc, _SLUG_UNIQUE_CONSTRAINT):
            raise DuplicateSlug() from exc
        raise


async def list_tenants(session: AsyncSession) -> list[TenantRecord]:
    """Todos los tenants, más reciente primero (spec S4.1 §3 C7). Solo lectura."""
    return await repository.list_tenants(session)


async def convert_to_production(session: AsyncSession, tenant_id: UUID) -> TenantRecord:
    """Pone `is_demo=false` (S4.4, spec §0 decisión 2). Idempotente si ya era producción; id
    inexistente -> `TenantNotFound`."""
    record = await repository.convert_tenant_to_production(session, tenant_id)
    if record is None:
        raise TenantNotFound()
    return record


async def purge_demo_tenant(session: AsyncSession, tenant_id: UUID) -> None:
    """Borra un tenant demo por completo: fila + cascada + bucket de MinIO (S4.4, spec §0 decisión
    3). Id inexistente -> `TenantNotFound`; existe pero no es demo -> `TenantNotDemo` (nunca se
    borra un tenant de producción por esta vía).

    La condición "solo demo" y la comprobación de existencia viven en una única sentencia atómica
    dentro de la función SQL `purge_demo_tenant` (`SELECT ... FOR UPDATE` + `DELETE`, migración
    0011): sin pre-chequeo aparte en Python, así que no hay ninguna carrera posible entre
    "comprobar" y "borrar" bajo peticiones concurrentes sobre el mismo tenant.
    """
    outcome = await repository.purge_demo_tenant(session, tenant_id)
    if not outcome.existed:
        raise TenantNotFound()
    if not outcome.was_demo:
        raise TenantNotDemo()

    intake_service.schedule_bucket_cleanup(session, storage.bucket_for(tenant_id))


async def tenant_metrics(session: AsyncSession) -> list[repository.TenantMetrics]:
    """Consumo agregado de todos los tenants (S4.5 §3 C1-C4). Solo lectura."""
    return await repository.tenant_metrics(session)

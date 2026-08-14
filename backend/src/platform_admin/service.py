"""Lógica de dominio del alta/listado de tenants (S4.1): validación de slug/color y traducción de
la violación del UNIQUE de `tenants.slug` a un error de dominio. El router es fino; el SQL vive en
`repository` (funciones `SECURITY DEFINER`).
"""

from __future__ import annotations

import contextlib
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_intake import service as intake_service
from invoice_intake import storage
from platform_admin import repository
from platform_admin.export import TENANT_TABLES, build_tenant_export_zip, extension_for_content_type
from platform_admin.repository import TenantRecord
from shared.config import get_settings
from shared.db import tenant_session
from shared.encryption import tenant_encryption_key
from shared.integrity import violates_unique_constraint
from tenancy.constants import RESERVED_SLUGS
from tenancy.resolution import is_root_or_reserved_host

_EXPORT_URL_TTL_SECONDS = 3600  # 1h: fichero más grande que las descargas de un objeto (S2.7).

# Etiqueta DNS de primer nivel (el slug se usa tal cual como subdominio): minúsculas, dígitos y
# guiones, sin empezar/terminar en guión, 1-63 caracteres. La longitud se valida aquí (no solo se
# delega a la columna, `String(63)`): un slug de formato válido pero más largo violaría la columna
# con un `DataError` de Postgres (500), no el 422 que documenta la spec (S4.1 §3 C3).
_SLUG_FORMAT = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

# `#RRGGBB` o `#RRGGBBAA` (con canal alfa opcional), coherente con `tenant_branding.color_*`
# (String(9): 1 `#` + hasta 8 hex).
_COLOR_FORMAT = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")

# FQDN de al menos dos etiquetas (nunca un slug suelto): letras/dígitos/guiones por etiqueta, sin
# empezar/terminar en guión, separadas por puntos. No exige que cuelgue de un dominio de terceros
# a propósito (spec S4.6 §3 decisión 4: el caso de prueba interno cuelga de `autoken.es`).
_CUSTOM_DOMAIN_FORMAT = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)

_SLUG_UNIQUE_CONSTRAINT = "tenants_slug_key"
_CUSTOM_DOMAIN_UNIQUE_CONSTRAINT = "tenants_custom_domain_key"


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


class InvalidCustomDomain(PlatformError):
    """El dominio propio no tiene forma de FQDN válida (-> 422, S4.6)."""


class DuplicateCustomDomain(PlatformError):
    """Ya existe un tenant con ese dominio propio (-> 409, S4.6)."""


class TenantSlugMismatch(PlatformError):
    """El `confirm_slug` del borrado no coincide con el slug real del tenant (-> 422, S4.7)."""


class TenantExportRequired(PlatformError):
    """El tenant nunca se exportó: no se puede borrar sin un export previo (-> 409, S4.7)."""


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


def _validated_custom_domain(custom_domain: str | None) -> str | None:
    if custom_domain is None:
        return None
    # Minúsculas antes de validar/guardar: DNS es insensible a mayúsculas y la resolución
    # (`resolve_tenant_by_custom_domain`) normaliza el `Host` real a minúsculas, así que guardar
    # tal cual `Facturas.Cliente.ES` dejaría el dominio asignado sin poder resolver nunca.
    canonical = custom_domain.lower()
    if not _CUSTOM_DOMAIN_FORMAT.match(canonical):
        raise InvalidCustomDomain
    # El dominio raíz o un subdominio reservado de plataforma (`autoken.es`, `panel.autoken.es`...)
    # nunca llega a intentar la resolución por dominio propio (`is_root_or_reserved_host`, mismo
    # guard que usa el middleware) — guardarlo igualmente dejaría una configuración muerta desde el
    # instante en que se asigna, sin ningún aviso. Mismo criterio que `_validated_slug` ya aplica a
    # `RESERVED_SLUGS` para el caso análogo del slug.
    if is_root_or_reserved_host(canonical, get_settings().base_domain, allow_localhost=False):
        raise InvalidCustomDomain
    return canonical


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


async def set_custom_domain(
    session: AsyncSession, tenant_id: UUID, custom_domain: str | None
) -> TenantRecord:
    """Asigna o quita (`None`) el dominio propio de un tenant (S4.6). Formato inválido ->
    `InvalidCustomDomain`; id inexistente -> `TenantNotFound`; duplicado ->
    `DuplicateCustomDomain`."""
    canonical = _validated_custom_domain(custom_domain)
    try:
        record = await repository.set_tenant_custom_domain(session, tenant_id, canonical)
    except IntegrityError as exc:
        if violates_unique_constraint(exc, _CUSTOM_DOMAIN_UNIQUE_CONSTRAINT):
            raise DuplicateCustomDomain() from exc
        raise
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


async def suspend_tenant(session: AsyncSession, tenant_id: UUID) -> TenantRecord:
    """Bloquea el login de todos los usuarios del tenant sin tocar ningún dato (S4.7 §3 decisión
    1). Idempotente si ya estaba suspendido; id inexistente -> `TenantNotFound`."""
    record = await repository.suspend_tenant(session, tenant_id)
    if record is None:
        raise TenantNotFound()
    return record


async def reactivate_tenant(session: AsyncSession, tenant_id: UUID) -> TenantRecord:
    """Revierte `suspend_tenant` (S4.7 §3 decisión 1). Idempotente si ya estaba activo; id
    inexistente -> `TenantNotFound`."""
    record = await repository.reactivate_tenant(session, tenant_id)
    if record is None:
        raise TenantNotFound()
    return record


async def export_tenant(session: AsyncSession, tenant_id: UUID) -> str:
    """Genera el ZIP completo del tenant (BD + ficheros), lo sube a `PLATFORM_EXPORTS_BUCKET` y
    marca `last_export_at` (S4.7 §3 decisión 2). Devuelve la URL de descarga firmada. Id
    inexistente -> `TenantNotFound`.

    Lee la BD del tenant abriendo su PROPIA `tenant_session` (no la sesión de plataforma del
    llamador, que no tiene `app.tenant_id` fijado): la RLS de dos niveles ya acota el resultado a
    ese tenant completo (`company_id` sin fijar = todas las empresas), sin necesitar una función
    `SECURITY DEFINER` de lectura por tabla (spec §0).
    """
    tenants = await repository.list_tenants(session)
    if not any(t.id == tenant_id for t in tenants):
        raise TenantNotFound()

    encryption_key = tenant_encryption_key(get_settings(), tenant_id)
    async with tenant_session(tenant_id) as ts:
        tables = {
            table: await repository.fetch_tenant_table_rows(
                ts, table, encryption_key=encryption_key
            )
            for table in TENANT_TABLES
        }

    files: list[tuple[str, bytes]] = []
    for uploaded_file in tables["uploaded_files"]:
        content = storage.get_object(uploaded_file["storage_bucket"], uploaded_file["storage_key"])
        extension = extension_for_content_type(uploaded_file["content_type"])
        files.append((f"{uploaded_file['id']}{extension}", content))
    for page in tables["uploaded_file_pages"]:
        content = storage.get_object(page["storage_bucket"], page["storage_key"])
        extension = extension_for_content_type(page["content_type"])
        files.append(
            (f"{page['root_uploaded_file_id']}-page-{page['page_number']}{extension}", content)
        )

    zip_bytes = build_tenant_export_zip(tables, files)
    # Sufijo aleatorio, no solo el timestamp (hallazgo real de la auditoría de cobertura, verificado
    # con un test que reprodujo el bug): dos exports dentro del mismo segundo generaban la MISMA
    # clave y el segundo pisaba en silencio el ZIP del primero en MinIO. `uuid4` hace la colisión
    # estructuralmente imposible, no solo improbable.
    timestamp = f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
    export_key = storage.export_key_for(tenant_id, timestamp)
    storage.put_object(
        storage.PLATFORM_EXPORTS_BUCKET, export_key, zip_bytes, len(zip_bytes), "application/zip"
    )
    download_url = storage.presigned_get_url(
        storage.PLATFORM_EXPORTS_BUCKET, export_key, _EXPORT_URL_TTL_SECONDS
    )

    marked_at = await repository.mark_tenant_exported(session, tenant_id)
    if marked_at is None:
        # El tenant se borró concurrentemente mientras se generaba este export (posible solo si ya
        # tenía uno anterior: `delete_tenant` exige un export previo). El ZIP ya subido quedaría
        # huérfano en `PLATFORM_EXPORTS_BUCKET`, sin URL entregada a nadie (hallazgo de la
        # auditoría de seguridad) — se borra por compensación antes de propagar el 404.
        with contextlib.suppress(storage.StorageUnavailable):
            storage.remove_object(storage.PLATFORM_EXPORTS_BUCKET, export_key)
        raise TenantNotFound()
    return download_url


async def delete_tenant(session: AsyncSession, tenant_id: UUID, confirm_slug: str) -> None:
    """Borra un tenant entero: fila + cascada + bucket de MinIO (S4.7 §3 decisión 4). Id
    inexistente -> `TenantNotFound`; `confirm_slug` no coincide -> `TenantSlugMismatch`; sin
    ningún export previo -> `TenantExportRequired`.

    La condición completa (existe, el slug coincide, hay un export previo) vive en una única
    sentencia SQL atómica dentro de `delete_tenant` (`SELECT ... FOR UPDATE` + `DELETE`, migración
    0015) — mismo patrón que `purge_demo_tenant` (S4.4), sin pre-chequeo aparte en Python.
    """
    outcome = await repository.delete_tenant(session, tenant_id, confirm_slug)
    if not outcome.existed:
        raise TenantNotFound()
    if not outcome.slug_matched:
        raise TenantSlugMismatch()
    if not outcome.exported:
        raise TenantExportRequired()

    intake_service.schedule_bucket_cleanup(session, storage.bucket_for(tenant_id))

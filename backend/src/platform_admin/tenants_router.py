"""Endpoints HTTP del alta/listado de tenants (S4.1): `POST`/`GET /api/v1/platform/tenants`.

Capa HTTP fina: autentica y autoriza (`platform_admin`, `current_platform_identity`, distinta de
`current_identity` porque un `platform_admin` no tiene tenant), tipa el body y traduce el resultado
o la excepción de dominio de `platform_admin.service` a la respuesta. Sin SQL ni reglas de negocio.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from identity.authz import require_platform_admin
from identity.dependencies import PlatformAuthContext
from invoice_intake.storage import StorageUnavailable
from platform_admin import logo_upload, service
from platform_admin.repository import TenantMetrics, TenantRecord

router = APIRouter(prefix="/platform/tenants", tags=["platform"])

Platform = Annotated[PlatformAuthContext, Depends(require_platform_admin())]


class TenantCreateIn(BaseModel):
    """Cuerpo de `POST /platform/tenants` (spec S4.1 §2/§3, `is_demo` desde S4.4)."""

    name: str
    slug: str
    logo_url: str | None = None
    color_primary: str | None = None
    color_secondary: str | None = None
    is_demo: bool = False


class TenantOut(BaseModel):
    """Un tenant en la respuesta (alta/listado/conversión a producción). `custom_domain` (S4.6)
    solo `POST /platform/tenants` (alta) lo devuelve siempre `None`: un tenant recién creado
    nunca tuvo tiempo de que se le asignara uno (spec §3 decisión 3)."""

    id: UUID
    slug: str
    name: str
    status: str
    is_demo: bool
    created_at: datetime
    custom_domain: str | None = None


def _to_out(record: TenantRecord) -> TenantOut:
    return TenantOut(
        id=record.id,
        slug=record.slug,
        name=record.name,
        status=record.status,
        is_demo=record.is_demo,
        created_at=record.created_at,
        custom_domain=record.custom_domain,
    )


class CustomDomainIn(BaseModel):
    """Cuerpo de `PATCH /platform/tenants/{tenant_id}/custom-domain` (S4.6). `None` lo quita."""

    custom_domain: str | None = None


class ExportOut(BaseModel):
    """Respuesta de `POST /platform/tenants/{tenant_id}/export` (S4.7)."""

    download_url: str


class DeleteTenantIn(BaseModel):
    """Cuerpo de `DELETE /platform/tenants/{tenant_id}` (S4.7): segundo factor de confirmación
    verificado en servidor, spec §3 decisión 4."""

    confirm_slug: str


class TenantMetricsOut(BaseModel):
    """Consumo agregado de un tenant (S4.5). `ocr_extractions_count` es un proxy de uso, nunca una
    cifra monetaria (spec §0 decisión 1: no hay coste real en € disponible hoy)."""

    tenant_id: UUID
    slug: str
    name: str
    companies_count: int
    admins_count: int
    users_count: int
    invoices_this_month: int
    invoices_total_count: int
    ocr_extractions_count: int
    last_activity_at: datetime | None


def _metrics_to_out(record: TenantMetrics) -> TenantMetricsOut:
    return TenantMetricsOut(
        tenant_id=record.tenant_id,
        slug=record.slug,
        name=record.name,
        companies_count=record.companies_count,
        admins_count=record.admins_count,
        users_count=record.users_count,
        invoices_this_month=record.invoices_this_month,
        invoices_total_count=record.invoices_total_count,
        ocr_extractions_count=record.ocr_extractions_count,
        last_activity_at=record.last_activity_at,
    )


class LogoUploadOut(BaseModel):
    """Respuesta de `POST /platform/tenants/logo`: la URL pública lista para usar como `logo_url`
    en el alta/edición de un tenant (2026-08-01, decisión de Julio)."""

    logo_url: str


@router.post("/logo", status_code=201)
async def upload_logo(identity: Platform, file: UploadFile) -> LogoUploadOut:
    """Sube una imagen de logo (jpeg/png, máx. 2 MiB) y devuelve su URL pública.

    Antes de esto, `logo_url` solo admitía pegar una URL ya alojada en otro sitio. Mismo orden de
    validación que el intake de facturas (S2.1): vacío -> tamaño -> tipo real -> antivirus ->
    almacenar (spec, ver `logo_upload.upload_logo`)."""
    content = await file.read(logo_upload.MAX_LOGO_BYTES + 1)
    try:
        logo_url = await asyncio.to_thread(logo_upload.upload_logo, content)
    except logo_upload.LogoEmpty as exc:
        raise HTTPException(status_code=422, detail="El fichero está vacío") from exc
    except logo_upload.LogoTooLarge as exc:
        raise HTTPException(
            status_code=413,
            detail=f"El logo supera el tamaño máximo ({logo_upload.MAX_LOGO_BYTES} bytes)",
        ) from exc
    except logo_upload.LogoTypeNotAllowed as exc:
        raise HTTPException(status_code=415, detail="Solo se admiten imágenes JPEG o PNG") from exc
    except logo_upload.ScanInfected as exc:
        raise HTTPException(status_code=422, detail="El fichero no pasó el antivirus") from exc
    except logo_upload.ScannerUnavailable as exc:
        raise HTTPException(status_code=503, detail="Antivirus no disponible") from exc
    except StorageUnavailable as exc:
        raise HTTPException(status_code=503, detail="Almacén de ficheros no disponible") from exc
    return LogoUploadOut(logo_url=logo_url)


@router.post("", status_code=201)
async def create_tenant(identity: Platform, body: TenantCreateIn) -> TenantOut:
    """Da de alta un tenant operativo (S4.1). Slug/color inválidos -> 422; slug duplicado -> 409."""
    try:
        record = await service.create_tenant(
            identity.session,
            name=body.name,
            slug=body.slug,
            logo_url=body.logo_url,
            color_primary=body.color_primary,
            color_secondary=body.color_secondary,
            is_demo=body.is_demo,
        )
    except service.InvalidName as exc:
        raise HTTPException(status_code=422, detail="El nombre no puede estar vacío") from exc
    except service.InvalidSlug as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except service.InvalidColor as exc:
        raise HTTPException(
            status_code=422, detail="El color debe ser hexadecimal (#RRGGBB o #RRGGBBAA)"
        ) from exc
    except service.DuplicateSlug as exc:
        raise HTTPException(status_code=409, detail="Ya existe un tenant con ese slug") from exc
    return _to_out(record)


@router.get("")
async def list_tenants(identity: Platform) -> list[TenantOut]:
    """Todos los tenants, más reciente primero (S4.1)."""
    records = await service.list_tenants(identity.session)
    return [_to_out(record) for record in records]


@router.get("/metrics")
async def tenant_metrics(identity: Platform) -> list[TenantMetricsOut]:
    """Consumo agregado de todos los tenants, ordenado por slug (S4.5)."""
    records = await service.tenant_metrics(identity.session)
    return [_metrics_to_out(record) for record in records]


@router.post("/{tenant_id}/convert-to-production")
async def convert_to_production(identity: Platform, tenant_id: UUID) -> TenantOut:
    """Pone `is_demo=false` (S4.4). Idempotente si ya era producción; id inexistente -> 404."""
    try:
        record = await service.convert_to_production(identity.session, tenant_id)
    except service.TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="No existe ese tenant") from exc
    return _to_out(record)


@router.post("/{tenant_id}/purge", status_code=204)
async def purge_demo_tenant(identity: Platform, tenant_id: UUID) -> None:
    """Borra un tenant demo por completo (S4.4). Id inexistente -> 404; no es demo -> 409."""
    try:
        await service.purge_demo_tenant(identity.session, tenant_id)
    except service.TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="No existe ese tenant") from exc
    except service.TenantNotDemo as exc:
        raise HTTPException(status_code=409, detail="Solo se pueden purgar tenants demo") from exc


@router.patch("/{tenant_id}/custom-domain")
async def set_custom_domain(identity: Platform, tenant_id: UUID, body: CustomDomainIn) -> TenantOut:
    """Asigna o quita (`null`) el dominio propio de un tenant (S4.6, alcance acotado — ver spec
    §0). Formato inválido -> 422; id inexistente -> 404; duplicado -> 409."""
    try:
        record = await service.set_custom_domain(identity.session, tenant_id, body.custom_domain)
    except service.InvalidCustomDomain as exc:
        raise HTTPException(
            status_code=422, detail="El dominio propio no tiene formato válido"
        ) from exc
    except service.TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="No existe ese tenant") from exc
    except service.DuplicateCustomDomain as exc:
        raise HTTPException(
            status_code=409, detail="Ya existe un tenant con ese dominio propio"
        ) from exc
    return _to_out(record)


@router.post("/{tenant_id}/suspend")
async def suspend_tenant(identity: Platform, tenant_id: UUID) -> TenantOut:
    """Bloquea el login de todos los usuarios del tenant, sin tocar datos (S4.7). Idempotente si
    ya estaba suspendido; id inexistente -> 404."""
    try:
        record = await service.suspend_tenant(identity.session, tenant_id)
    except service.TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="No existe ese tenant") from exc
    return _to_out(record)


@router.post("/{tenant_id}/reactivate")
async def reactivate_tenant(identity: Platform, tenant_id: UUID) -> TenantOut:
    """Revierte `suspend` (S4.7). Idempotente si ya estaba activo; id inexistente -> 404."""
    try:
        record = await service.reactivate_tenant(identity.session, tenant_id)
    except service.TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="No existe ese tenant") from exc
    return _to_out(record)


@router.post("/{tenant_id}/export")
async def export_tenant(identity: Platform, tenant_id: UUID) -> ExportOut:
    """Genera un ZIP completo (BD + ficheros) del tenant y devuelve una URL de descarga firmada
    (S4.7). Id inexistente -> 404."""
    try:
        download_url = await service.export_tenant(identity.session, tenant_id)
    except service.TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="No existe ese tenant") from exc
    return ExportOut(download_url=download_url)


@router.delete("/{tenant_id}", status_code=204)
async def delete_tenant(identity: Platform, tenant_id: UUID, body: DeleteTenantIn) -> None:
    """Borra un tenant entero (S4.7, alcance real: no solo demo, a diferencia de `purge`). Id
    inexistente -> 404; `confirm_slug` no coincide -> 422; sin ningún export previo -> 409."""
    try:
        await service.delete_tenant(identity.session, tenant_id, body.confirm_slug)
    except service.TenantNotFound as exc:
        raise HTTPException(status_code=404, detail="No existe ese tenant") from exc
    except service.TenantSlugMismatch as exc:
        raise HTTPException(
            status_code=422, detail="El nombre de confirmación no coincide con el slug del tenant"
        ) from exc
    except service.TenantExportRequired as exc:
        raise HTTPException(
            status_code=409, detail="Hace falta exportar el tenant antes de poder borrarlo"
        ) from exc

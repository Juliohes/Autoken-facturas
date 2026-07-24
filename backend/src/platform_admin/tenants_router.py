"""Endpoints HTTP del alta/listado de tenants (S4.1): `POST`/`GET /api/v1/platform/tenants`.

Capa HTTP fina: autentica y autoriza (`platform_admin`, `current_platform_identity`, distinta de
`current_identity` porque un `platform_admin` no tiene tenant), tipa el body y traduce el resultado
o la excepción de dominio de `platform_admin.service` a la respuesta. Sin SQL ni reglas de negocio.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from identity.authz import require_platform_admin
from identity.dependencies import PlatformAuthContext
from platform_admin import service
from platform_admin.repository import TenantRecord

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
    """Un tenant en la respuesta (alta o listado)."""

    id: UUID
    slug: str
    name: str
    status: str
    is_demo: bool
    created_at: datetime


def _to_out(record: TenantRecord) -> TenantOut:
    return TenantOut(
        id=record.id,
        slug=record.slug,
        name=record.name,
        status=record.status,
        is_demo=record.is_demo,
        created_at=record.created_at,
    )


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
        raise HTTPException(
            status_code=409, detail="Solo se pueden purgar tenants demo"
        ) from exc

"""Endpoints de tenancy expuestos por la API (S1.2, ampliado con branding en S4.2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from tenancy import repository
from tenancy.context import PublicTenantContext, public_tenant_context

router = APIRouter(tags=["tenancy"])

# Mismo patrón que el registro público (S1.4): sin token, contexto abierto desde el subdominio.
PublicContext = Annotated[PublicTenantContext, Depends(public_tenant_context)]


class TenantCurrentOut(BaseModel):
    """Respuesta de `GET /tenants/current` (S1.2 + branding S4.2).

    Los campos de branding son `null` cuando el tenant no tiene fila en `tenant_branding` o el campo
    concreto está vacío: el servidor nunca inventa un valor por defecto (spec S4.2 decisión 1); los
    valores de reemplazo ("Setex tal cual hoy") los aplica el frontend.
    """

    slug: str
    name: str
    is_demo: bool
    logo_url: str | None
    color_primary: str | None
    color_secondary: str | None
    app_name: str | None
    favicon: str | None


@router.get("/tenants/current")
async def current_tenant(context: PublicContext) -> TenantCurrentOut:
    """Datos públicos del tenant resuelto por el subdominio, incluido su branding (S1.2/S4.2).

    404 neutro si el host no corresponde a un tenant activo (inexistente, suspendido o no-tenant):
    la respuesta es idéntica en todos esos casos, no se revela qué tenants existen (lo da
    `public_tenant_context`, mismo portero que el registro público, S1.4).
    """
    tenant = context.tenant
    branding = await repository.get_branding(context.session, tenant.id)
    return TenantCurrentOut(
        slug=tenant.slug,
        name=tenant.name,
        is_demo=tenant.is_demo,
        logo_url=branding.logo_url if branding else None,
        color_primary=branding.color_primary if branding else None,
        color_secondary=branding.color_secondary if branding else None,
        app_name=branding.app_name if branding else None,
        favicon=branding.favicon if branding else None,
    )

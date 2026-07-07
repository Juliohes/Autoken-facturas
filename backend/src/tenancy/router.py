"""Endpoints de tenancy expuestos por la API (S1.2)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from tenancy.resolution import ResolvedTenant

router = APIRouter(tags=["tenancy"])


@router.get("/tenants/current")
async def current_tenant(request: Request) -> dict[str, object]:
    """Datos públicos del tenant resuelto por el subdominio (para el login/branding).

    404 neutro si el host no corresponde a un tenant activo (inexistente, suspendido o no-tenant):
    la respuesta es idéntica en todos esos casos, no se revela qué tenants existen.
    """
    tenant: ResolvedTenant | None = getattr(request.state, "tenant", None)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return {"slug": tenant.slug, "name": tenant.name, "is_demo": tenant.is_demo}

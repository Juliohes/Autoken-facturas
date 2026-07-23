"""Contexto de tenant SIN token para rutas públicas del subdominio (S1.4/S4.2).

Vive en `tenancy` (no en `identity`) porque no depende de nada de autenticación: solo del tenant ya
resuelto por el middleware de subdominio (S1.2). Dos consumidores hoy: el registro público (S1.4,
`identity/registration_router.py`, escribe usuario+empresa+membership) y `GET /tenants/current`
(S4.2, `tenancy/router.py`, solo lee su branding) — mismo patrón, "abrir el contexto de aislamiento
sin token", reutilizado en vez de reimplementado en cada router público.

Si el host no resuelve a un tenant activo (raíz, plataforma, inexistente o suspendido) no hay
asesoría con la que trabajar -> **404** (nunca 500).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db import tenant_session
from tenancy.resolution import ResolvedTenant


@dataclass(frozen=True)
class PublicTenantContext:
    """Tenant del subdominio + su sesión de BD abierta en contexto de aislamiento (sin token)."""

    tenant: ResolvedTenant
    session: AsyncSession


async def public_tenant_context(request: Request) -> AsyncIterator[PublicTenantContext]:
    """Resuelve el tenant del subdominio y cede una sesión dentro de `tenant_session` (o 404)."""
    resolved: ResolvedTenant | None = getattr(request.state, "tenant", None)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Not found")
    async with tenant_session(resolved.id) as session:
        yield PublicTenantContext(tenant=resolved, session=session)

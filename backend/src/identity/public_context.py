"""Contexto de tenant SIN token para rutas públicas del subdominio (S1.4: registro).

El registro es **público** pero escribe SOLO en el tenant del subdominio: no hay token que porte el
`tenant_id`, así que el contexto de aislamiento se abre desde `request.state.tenant` (resuelto por
el middleware de S1.2). Si el host no resuelve a un tenant activo (raíz, plataforma, inexistente o
suspendido) no hay asesoría donde registrarse -> **404** (nunca 500). La sesión se abre en contexto
de asesoría (sin `company_id`): el registro crea usuario + empresa + membership del tenant, y el
`tenant_id` de esas filas sale del contexto (`app.tenant_id`), jamás del cliente.
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

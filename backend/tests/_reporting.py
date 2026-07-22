"""Utilidades de test compartidas del contexto `reporting` (panel S3.1 + export S3.2).

No es un módulo de tests (prefijo `_`): siembra de un `tenant_admin` con una empresa de su asesoría
ya lista para pedir el panel o el export, reutilizada por ambos.
"""

from __future__ import annotations

import httpx

from tests._dbtest import seed_company
from tests._intake import seed_tenant_admin, token_for


async def seed_admin_with_company(
    dsns: dict[str, str], client: httpx.AsyncClient, *, slug: str = "ilex"
) -> tuple[str, str, str, str]:
    """Siembra tenant + `tenant_admin` + una empresa de su asesoría. Devuelve
    (tenant_id, admin_id, company_id, token)."""
    tenant_id, admin_id = await seed_tenant_admin(dsns, slug=slug, email=f"admin@{slug}.es")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Empresa", cif="A39031620"
    )
    token = await token_for(client, email=f"admin@{slug}.es", hostname=f"{slug}.localhost")
    return tenant_id, admin_id, company_id, token

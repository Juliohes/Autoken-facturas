"""Acceso a datos del contexto `companies`: el SQL de `companies` vive aquí, no en el router.

La sesión llega ya abierta en el contexto de aislamiento por `current_identity` (S1.6): la RLS de
Postgres (ADR-0001) decide qué filas se ven. En contexto de asesoría (`tenant_admin`, sin
`app.company_id`) se ven todas las empresas del tenant; en contexto de empresa, solo la propia.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class CompanyRow:
    """Datos públicos de una empresa para el listado."""

    id: UUID
    name: str
    cif: str
    status: str


async def list_companies(session: AsyncSession) -> list[CompanyRow]:
    """Lista las empresas visibles en el contexto de la sesión, por nombre (la RLS acota)."""
    rows = (
        await session.execute(text("SELECT id, name, cif, status FROM companies ORDER BY name"))
    ).all()
    return [CompanyRow(id=r.id, name=r.name, cif=r.cif, status=r.status) for r in rows]

"""Descubrimiento de candidatos del backfill retroactivo de la comparativa (S2.10).

Llama a `ocr_backfill_candidates()` (migración 0018, `SECURITY DEFINER`), que lee A TRAVÉS de todos
los tenants qué ficheros ya procesados con éxito todavía no tienen comparativa — mismo patrón ya
auditado que `list_tenants`/`platform_tenant_metrics` (S4.1/S4.5) para leer cruzando la frontera de
tenant. Solo lectura: no escribe nada ni invoca al lector de IA (eso es el script de backfill, que
para cada candidato SÍ pasa por el camino normal con RLS de su propio tenant).

El filtro de "formato de imagen soportado" se aplica AQUÍ, en Python, contra
`ocr.preprocess.enhance.SUPPORTED_CONTENT_TYPES` — la función SQL solo filtra por estado, para no
duplicar esa lista en dos sitios sin guardarraíl que los mantenga sincronizados (auditoría).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ocr.preprocess.enhance import SUPPORTED_CONTENT_TYPES

__all__ = ["BackfillCandidate", "list_backfill_candidates"]


@dataclass(frozen=True)
class BackfillCandidate:
    tenant_id: UUID
    company_id: UUID
    uploaded_file_id: UUID


async def list_backfill_candidates(session: AsyncSession) -> list[BackfillCandidate]:
    """Ficheros elegibles para la comparativa (llamar desde `shared.db.platform_session`)."""
    rows = (
        await session.execute(
            text(
                "SELECT tenant_id, company_id, uploaded_file_id, content_type "
                "FROM ocr_backfill_candidates()"
            )
        )
    ).all()
    return [
        BackfillCandidate(
            tenant_id=row.tenant_id,
            company_id=row.company_id,
            uploaded_file_id=row.uploaded_file_id,
        )
        for row in rows
        if row.content_type in SUPPORTED_CONTENT_TYPES
    ]

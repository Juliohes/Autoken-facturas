"""Descubrimiento de candidatos del backfill retroactivo del ranking (S4.8).

Llama a `ocr_ranking_candidates()` (migración 0019, `SECURITY DEFINER`), que lee A TRAVÉS de todos
los tenants qué ficheros ya procesados con éxito todavía no tienen NINGUNA entrada de ranking —
mismo patrón que `ocr.backfill_repository` (S2.10). Solo lectura: no escribe nada ni invoca a
ningún motor.

A diferencia de S2.10 (realce de imagen, solo jpeg/png/webp), el ranking NO filtra por
`content_type` aquí: entre los 6 motores candidatos hay cobertura de imagen Y de PDF (Gemini/Claude
nativo, gpt-5.1 vía rasterización, Mistral vía `document_url`) — filtrar por el conjunto "solo
imagen" de S2.9 excluiría PDFs que sí son procesables. Cada motor valida su propio `content_type`
soportado al extraer (spec C4): un fichero en un formato que ningún motor soporta simplemente no
genera ninguna entrada, sin error visible.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["RankingBackfillCandidate", "list_ranking_backfill_candidates"]


@dataclass(frozen=True)
class RankingBackfillCandidate:
    tenant_id: UUID
    company_id: UUID
    uploaded_file_id: UUID


async def list_ranking_backfill_candidates(
    session: AsyncSession,
) -> list[RankingBackfillCandidate]:
    """Ficheros sin ninguna entrada de ranking todavía (llamar desde `platform_session`)."""
    rows = (
        await session.execute(
            text("SELECT tenant_id, company_id, uploaded_file_id FROM ocr_ranking_candidates()")
        )
    ).all()
    return [
        RankingBackfillCandidate(
            tenant_id=row.tenant_id,
            company_id=row.company_id,
            uploaded_file_id=row.uploaded_file_id,
        )
        for row in rows
    ]

"""Orquestación del backfill retroactivo del ranking multi-modelo (S4.8).

Mismo patrón que `jobs.ocr_backfill` (S2.10): descubre candidatos a través de todos los tenants
(`ocr.ranking_backfill_repository`, `SECURITY DEFINER`) y, en modo real, dispara el ranking fichero
a fichero por el MISMO camino que el job en vivo (`jobs.ocr_ranking.run_ocr_ranking`), sin duplicar
esa lógica. El modo simulación (por defecto en el CLI) no descarga ningún fichero ni invoca a ningún
motor: solo cuenta y registra los candidatos. Un fallo en UN candidato no aborta el resto del lote.

Coste de la ejecución real MAYOR que S2.10: hasta 5 motores extra por factura (frente a 1-2 de
S2.10), sobre el histórico completo de todos los tenants — decisión de coste explícita de Julio, no
de esta construcción (spec S4.8 §5/§6).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

from companies import repository as companies_repo
from invoice_intake import repository as intake_repo
from invoice_intake import storage
from jobs.ocr_ranking import run_ocr_ranking
from ocr.extraction import InvoiceExtractor
from ocr.ranking_backfill_repository import (
    RankingBackfillCandidate,
    list_ranking_backfill_candidates,
)
from ocr.ranking_engines import build_ranking_extractors
from shared.config import get_settings
from shared.db import platform_session, tenant_session

logger = structlog.get_logger(__name__)

__all__ = ["RankingBackfillSummary", "run_ranking_backfill"]


@dataclass(frozen=True)
class RankingBackfillSummary:
    candidates: int
    processed: int
    failed: int = 0


async def _fetch_candidates() -> list[RankingBackfillCandidate]:
    async with platform_session() as session:
        return await list_ranking_backfill_candidates(session)


async def _process_candidate(
    candidate: RankingBackfillCandidate, *, extractors: list[InvoiceExtractor]
) -> None:
    """Descarga el fichero y dispara el ranking por el mismo camino que el job en vivo."""
    async with tenant_session(candidate.tenant_id, candidate.company_id) as session:
        location = await intake_repo.get_file_location(session, candidate.uploaded_file_id)
        if location is None:
            logger.warning(
                "ranking_backfill.file_not_found",
                uploaded_file_id=str(candidate.uploaded_file_id),
            )
            return
        company = await companies_repo.get_company(session, candidate.company_id)
        if company is None:
            logger.warning(
                "ranking_backfill.company_not_found", company_id=str(candidate.company_id)
            )
            return

    content = await asyncio.to_thread(storage.get_object, location.bucket, location.key)
    await run_ocr_ranking(
        candidate.tenant_id,
        candidate.company_id,
        candidate.uploaded_file_id,
        content=content,
        content_type=location.content_type,
        own_cif=company.cif,
        extractors=extractors,
    )


async def run_ranking_backfill(
    *, execute: bool, rate_limit_seconds: float = 1.0
) -> RankingBackfillSummary:
    """Modo simulación (`execute=False`, por defecto): solo cuenta y registra candidatos, sin
    descargar nada ni llamar a ningún motor. Modo real (`execute=True`): SÍ dispara llamadas de
    pago; lo invoca explícitamente el CLI, nunca por defecto (spec S4.8 §5/§6)."""
    candidates = await _fetch_candidates()
    logger.info("ranking_backfill.candidates_found", count=len(candidates))

    if not execute:
        for candidate in candidates:
            logger.info(
                "ranking_backfill.candidate_dry_run",
                tenant_id=str(candidate.tenant_id),
                uploaded_file_id=str(candidate.uploaded_file_id),
            )
        return RankingBackfillSummary(candidates=len(candidates), processed=0)

    extractors = build_ranking_extractors(get_settings())
    processed = 0
    failed = 0
    for candidate in candidates:
        try:
            await _process_candidate(candidate, extractors=extractors)
            processed += 1
        except Exception as exc:  # noqa: BLE001  (un fichero problemático no aborta el histórico)
            failed += 1
            logger.error(
                "ranking_backfill.candidate_failed",
                uploaded_file_id=str(candidate.uploaded_file_id),
                error=str(exc),
            )
        if rate_limit_seconds > 0:
            await asyncio.sleep(rate_limit_seconds)
    return RankingBackfillSummary(candidates=len(candidates), processed=processed, failed=failed)

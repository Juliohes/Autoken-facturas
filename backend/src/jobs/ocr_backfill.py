"""Orquestación del backfill retroactivo de la comparativa original-vs-realzada (S2.10).

Vive en `jobs` (no en `ocr`) porque, igual que `jobs.ocr`, cablea I/O (MinIO, sesión de tenant) con
el dominio puro de `ocr` — y reutiliza `jobs.ocr.run_ocr_comparison` directamente: ambos módulos son
la misma capa de orquestación, así que este import no invierte la dirección de dependencias
`jobs -> ocr` que el resto del proyecto establece (auditoría, hallazgo de arquitectura).

Descubre candidatos a través de todos los tenants (`ocr.backfill_repository`, `SECURITY DEFINER`) y,
en modo real, dispara la comparativa fichero a fichero por el MISMO camino que el job en vivo, sin
duplicar esa lógica. El modo simulación (por defecto en el CLI,
`scripts/backfill_ocr_comparison.py`) no descarga ningún fichero ni invoca al lector de IA: solo
cuenta y registra los candidatos. En modo real, un fallo en UN candidato (fichero borrado de MinIO,
blip de red) no debe abortar el resto del histórico: se registra y se continúa con el siguiente.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

from companies import repository as companies_repo
from companies.service import tenant_encryption_key as company_encryption_key
from invoice_intake import repository as intake_repo
from invoice_intake import storage
from jobs.ocr import run_ocr_comparison
from ocr.backfill_repository import BackfillCandidate, list_backfill_candidates
from ocr.engines.gemini_extractor import build_default_extractor
from ocr.extraction import InvoiceExtractor
from shared.config import get_settings
from shared.db import platform_session, tenant_session

logger = structlog.get_logger(__name__)

__all__ = ["BackfillSummary", "run_backfill"]


@dataclass(frozen=True)
class BackfillSummary:
    candidates: int
    processed: int
    failed: int = 0


async def _fetch_candidates() -> list[BackfillCandidate]:
    async with platform_session() as session:
        return await list_backfill_candidates(session)


async def _process_candidate(candidate: BackfillCandidate, *, extractor: InvoiceExtractor) -> None:
    """Descarga el fichero y dispara la comparativa por el mismo camino que el job en vivo."""
    async with tenant_session(candidate.tenant_id, candidate.company_id) as session:
        location = await intake_repo.get_file_location(session, candidate.uploaded_file_id)
        if location is None:
            logger.warning(
                "backfill.file_not_found", uploaded_file_id=str(candidate.uploaded_file_id)
            )
            return
        company = await companies_repo.get_company(
            session,
            candidate.company_id,
            encryption_key=company_encryption_key(get_settings(), candidate.tenant_id),
        )
        if company is None:
            logger.warning("backfill.company_not_found", company_id=str(candidate.company_id))
            return

    content = await asyncio.to_thread(storage.get_object, location.bucket, location.key)
    await run_ocr_comparison(
        candidate.tenant_id,
        candidate.company_id,
        candidate.uploaded_file_id,
        content=content,
        content_type=location.content_type,
        own_cif=company.cif,
        extractor=extractor,
    )


async def run_backfill(*, execute: bool, rate_limit_seconds: float = 1.0) -> BackfillSummary:
    """Modo simulación (`execute=False`, por defecto en el CLI): solo cuenta y registra candidatos,
    sin descargar nada ni llamar al lector. Modo real (`execute=True`): SÍ dispara llamadas de pago;
    lo invoca explícitamente el CLI, nunca por defecto (spec S2.9/S2.10 §5/§6)."""
    candidates = await _fetch_candidates()
    logger.info("backfill.candidates_found", count=len(candidates))

    if not execute:
        for candidate in candidates:
            logger.info(
                "backfill.candidate_dry_run",
                tenant_id=str(candidate.tenant_id),
                uploaded_file_id=str(candidate.uploaded_file_id),
            )
        return BackfillSummary(candidates=len(candidates), processed=0)

    extractor = build_default_extractor(get_settings())
    processed = 0
    failed = 0
    for candidate in candidates:
        try:
            await _process_candidate(candidate, extractor=extractor)
            processed += 1
        except Exception as exc:  # noqa: BLE001  (un fichero problemático no aborta el histórico)
            failed += 1
            logger.error(
                "backfill.candidate_failed",
                uploaded_file_id=str(candidate.uploaded_file_id),
                error=str(exc),
            )
        if rate_limit_seconds > 0:
            await asyncio.sleep(rate_limit_seconds)
    return BackfillSummary(candidates=len(candidates), processed=processed, failed=failed)

"""Ranking multi-modelo (S4.8): job que compara varios motores OCR sobre la misma factura.

`run_ocr_ranking` es paralela y ortogonal a `jobs.ocr.run_ocr_comparison` (S2.10) — comparan ejes
distintos (S2.10: misma imagen, misma variante de un motor, original-vs-realzada; S4.8: misma
imagen original, N motores distintos) y viven en tablas separadas
(`ocr_comparison_runs`/`ocr_ranking_entries`), pero comparten el mismo interruptor
`platform_settings.ocr_experiment_enabled` (decisión ya tomada en el plan, no de esta tarea).

Reutiliza el análisis de dominio ya auditado (`ocr.analysis.analyze_invoice`,
`ocr.scoring.score_analysis`, `ocr.scoring.serialize_reading`) para puntuar y guardar cada
lectura — nunca inventa un criterio nuevo de "qué es una buena lectura".

Transacción PROPIA, llamada tras el resultado principal ya confirmado (desde `jobs.ocr.run_ocr`) o
de forma independiente desde el backfill retroactivo (`jobs.ocr_ranking_backfill`). El fallo de UN
motor (sin configurar o fallo puntual de esa factura) nunca bloquea a los demás (spec C3/C4); el
fallo de la orquestación entera nunca propaga al llamador (mismo criterio que C5 de S2.10).

`extractors` es un parámetro OBLIGATORIO, sin fallback interno a la config real (auditoría,
hallazgo alto): quien construye motores reales desde `.env` cuando el llamador no inyecta nada es
`jobs.ocr.run_ocr` (el único punto de producción legítimo para ese fallback), nunca esta función.
Así, llamar a `run_ocr_ranking` directamente (como hacen la mayoría de los tests) no puede disparar
llamadas de pago reales por omisión — el incidente real de S4.8 (ver docstring de
`jobs.ocr.run_ocr`) vivía precisamente en un fallback como este, un nivel más abajo de lo que
corresponde.

`counterparty_tax_id`/`counterparty_name` (S6.7 C24) viajan cifrados con la clave del tenant (mismo
patrón ADR-0018 que `jobs.ocr.run_ocr_comparison`): la clave se deriva UNA vez aquí (`tenant_id` ya
disponible) y se pasa a `_persist`, nunca se rederiva por cada motor.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from ocr import ranking_repository
from ocr.analysis import analyze_invoice
from ocr.extraction import DocumentPage, ExtractedInvoice, InvoiceExtractor, extract_document
from ocr.scoring import score_analysis, serialize_reading
from platform_admin import settings_repository
from shared.config import get_settings
from shared.db import tenant_session
from shared.encryption import tenant_encryption_key

logger = structlog.get_logger(__name__)

__all__ = ["run_ocr_ranking"]


async def run_ocr_ranking(
    tenant_id: UUID,
    company_id: UUID,
    uploaded_file_id: UUID,
    *,
    pages: list[DocumentPage],
    own_cif: str,
    extractors: list[InvoiceExtractor],
    default_reading: ExtractedInvoice | None = None,
) -> None:
    """Compara los motores candidatos disponibles sobre esta factura y guarda su ranking.

    `extractors`: motores a los que SÍ se les pide `.extract()` aquí (los tests inyectan dobles;
    `jobs.ocr.run_ocr` construye los reales desde la config cuando no le pasan nada).
    `default_reading` (S4.8, auditoría, hallazgo crítico): si el llamador ya tiene la lectura del
    motor por defecto (camino en vivo: `run_ocr` acaba de calcularla como `reconciled`),
    se reutiliza tal cual y NO se vuelve a pedir a Gemini Flash — pedirla otra vez pagaría esa
    llamada DOS veces por factura, el mismo bug de coste duplicado que ya se corrigió en S2.10 para
    `run_ocr_comparison`. Si es `None` (backfill retroactivo, sin ninguna lectura previa en
    memoria), el motor por defecto debe venir incluido en `extractors` para que se le llame también.
    Nunca propaga una excepción.
    """
    try:
        async with tenant_session(tenant_id, company_id) as session:
            settings_row = await settings_repository.get_settings(session)
            if not settings_row.ocr_experiment_enabled:
                return
            if not extractors and default_reading is None:
                return

        encryption_key = tenant_encryption_key(get_settings(), tenant_id)
        readings_to_persist: list[ExtractedInvoice] = []
        if default_reading is not None:
            readings_to_persist.append(default_reading)

        # Los proveedores pueden tardar segundos y cobrar dinero: no retienen una conexión del pool.
        readings = await asyncio.gather(
            *(extract_document(engine, pages) for engine in extractors), return_exceptions=True
        )
        for reading in readings:
            if isinstance(reading, BaseException):
                logger.error("ranking.engine_failed", uploaded_file_id=str(uploaded_file_id))
                continue
            readings_to_persist.append(reading)

        async with tenant_session(tenant_id, company_id) as session:
            for reading in readings_to_persist:
                await _persist(
                    session, company_id, uploaded_file_id, own_cif, reading, encryption_key
                )
    except Exception:  # noqa: BLE001  (experimento de fondo: nunca debe tumbar al llamador)
        logger.error("ranking.failed", uploaded_file_id=str(uploaded_file_id))


async def _persist(
    session: AsyncSession,
    company_id: UUID,
    uploaded_file_id: UUID,
    own_cif: str,
    reading: ExtractedInvoice,
    encryption_key: str,
) -> None:
    analysis = analyze_invoice(reading, own_cif)
    await ranking_repository.upsert_ranking_entry(
        session,
        company_id=company_id,
        uploaded_file_id=uploaded_file_id,
        engine=reading.engine,
        model=reading.model,
        reading=serialize_reading(reading, analysis),
        score=score_analysis(analysis),
        encryption_key=encryption_key,
    )

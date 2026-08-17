"""Recuperación periódica durable de OCR pendiente o con lease vencido (S6.13)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from jobs import queue
from shared.config import get_settings
from shared.db import platform_session


@dataclass(frozen=True)
class OcrRecoveryMetrics:
    """Contadores globales persistidos, sin PII ni etiquetas de tenant."""

    pending: int
    processing: int
    abandoned: int
    failed: int


async def recover_ocr_documents() -> OcrRecoveryMetrics:
    """Encola candidatos recuperables; el claim transaccional decide quién los procesa."""
    async with platform_session() as session:
        candidates = (
            await session.execute(
                text("SELECT * FROM public.ocr_recovery_candidates(:limit)"),
                {"limit": get_settings().ocr_recovery_batch_size},
            )
        ).all()
        metrics = (
            await session.execute(
                text(
                    "SELECT pending, processing, abandoned, failed FROM ocr_recovery_metrics "
                    "WHERE id = true"
                )
            )
        ).one()

    for candidate in candidates:
        await queue.enqueue_ocr(
            candidate.tenant_id, candidate.company_id, candidate.uploaded_file_id
        )
    return OcrRecoveryMetrics(
        pending=metrics.pending,
        processing=metrics.processing,
        abandoned=metrics.abandoned,
        failed=metrics.failed,
    )


async def read_ocr_recovery_metrics() -> OcrRecoveryMetrics | None:
    """Lee la última instantánea durable para Prometheus, sin escanear documentos en cada scrape."""
    async with platform_session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT pending, processing, abandoned, failed FROM ocr_recovery_metrics "
                    "WHERE id = true"
                )
            )
        ).first()
    if row is None:
        return None
    return OcrRecoveryMetrics(
        pending=row.pending,
        processing=row.processing,
        abandoned=row.abandoned,
        failed=row.failed,
    )


async def recover_ocr_task(_ctx: dict[str, Any]) -> None:
    """Adaptador ARQ del recuperador periódico, sin parámetros de cliente."""
    await recover_ocr_documents()

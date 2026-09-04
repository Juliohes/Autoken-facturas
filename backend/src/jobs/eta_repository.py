"""Persistencia de muestras agregadas usadas por la ETA (R-048)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text

from shared.db import platform_session


@dataclass(frozen=True)
class EtaSamples:
    queue_wait_seconds: list[float]
    processing_seconds: list[float]


async def record_sample(
    *,
    engine: str,
    model: str,
    page_count_bucket: str,
    status: str,
    queue_wait_seconds: float,
    processing_seconds: float,
) -> None:
    """Guarda una muestra sin PII; un fallo de telemetría nunca tumba el OCR."""
    async with platform_session() as session:
        await session.execute(
            text(
                "SELECT public.record_ocr_processing_sample(:engine, :model, :bucket, :status, "
                ":queue_wait, :processing)"
            ),
            {
                "engine": engine,
                "model": model,
                "bucket": page_count_bucket,
                "status": status,
                "queue_wait": max(queue_wait_seconds, 0.0),
                "processing": max(processing_seconds, 0.0),
            },
        )


async def get_samples(*, engine: str, model: str, page_count_bucket: str) -> EtaSamples:
    async with platform_session() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT queue_wait_seconds, processing_seconds "
                    "FROM public.ocr_processing_samples "
                    "WHERE engine = :engine AND model = :model "
                    "AND page_count_bucket = :bucket "
                    "AND completed_at >= now() - interval '30 days' "
                    "AND status <> 'failed' "
                    "ORDER BY completed_at DESC LIMIT 1000"
                ),
                {"engine": engine, "model": model, "bucket": page_count_bucket},
            )
        ).all()
    return EtaSamples(
        queue_wait_seconds=[float(row.queue_wait_seconds) for row in rows],
        processing_seconds=[float(row.processing_seconds) for row in rows],
    )

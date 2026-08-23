"""Endpoint `GET /metrics` (S5.6): agrega el contador HTTP transversal (`shared.metrics`) con la
salud de la cola OCR (`jobs.monitoring`) en un único texto Prometheus.

Vive en `jobs`, no en `shared`, a propósito (auditoría de arquitectura S5.6): `shared` es la capa
fundacional de la que dependen los contextos de dominio, nunca al revés; este endpoint SÍ conoce un
detalle de dominio concreto (la cola OCR de arq), así que el punto de composición que junta ambas
fuentes vive en `jobs`, que ya depende de `shared` (no genera dependencia circular).

`GET /metrics` es público (sin autenticación de aplicación, spec §4): es el criterio estándar del
ecosistema Prometheus, protegido a nivel de red en producción (solo el Prometheus interno lo
alcanza), nunca expone datos de negocio de un tenant (solo agregados operativos transversales).
"""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Gauge, generate_latest
from sqlalchemy.pool import QueuePool

from jobs.monitoring import ocr_queue_health
from jobs.ocr_recovery import read_ocr_recovery_metrics
from jobs.retention import read_retention_metrics
from shared.config import Settings, get_settings
from shared.db import get_engine
from shared.metrics import pending_count, ready_count

router = APIRouter(tags=["observability"])

ocr_queue_depth = Gauge(
    "autoken_ocr_queue_depth",
    "Trabajos OCR pendientes (aún no empezados) en la cola de arq",
)
ocr_documents = Gauge(
    "autoken_ocr_documents",
    "Documentos OCR por estado operativo, instantánea durable sin PII",
    ["state"],
)
expired_pending_metric = Gauge(
    "autoken_expired_pending_count",
    "Documentos no confirmados eliminados por la retención de 90 días",
)
purge_storage_failures_metric = Gauge(
    "autoken_purge_storage_failures",
    "Fallos al eliminar objetos después de una purga DB-first",
)
db_pool_size_metric = Gauge(
    "autoken_db_pool_size",
    "Conexiones persistentes configuradas en el pool de Postgres",
)
db_pool_checked_out_metric = Gauge(
    "autoken_db_pool_checked_out",
    "Conexiones del pool de Postgres actualmente prestadas",
)
db_pool_overflow_metric = Gauge(
    "autoken_db_pool_overflow",
    "Conexiones temporales de overflow actualmente prestadas",
)
db_pool_capacity_metric = Gauge(
    "autoken_db_pool_capacity",
    "Capacidad máxima configurada del pool de Postgres",
)
ocr_queue_backend_up = Gauge(
    "autoken_ocr_queue_backend_up",
    "Disponibilidad agregada de Redis/arq para la cola OCR",
)

_OLDEST_PENDING_METRIC = b"autoken_ocr_queue_oldest_pending_seconds"


def _render_oldest_pending_line(age_seconds: float) -> bytes:
    """Bloque de texto Prometheus (HELP+TYPE+valor) para la antigüedad del más viejo pendiente.

    Se ensambla a mano, en vez de con un `Gauge` normal, para que la métrica desaparezca de verdad
    cuando la cola está vacía (spec C6): un `Gauge` conservaría el último valor visto para siempre
    aunque la cola se vaciara, leyéndose como "el más viejo lleva X segundos" cuando en realidad no
    hay ninguno. NO convertir esto a un `Gauge.set()` normal sin releer C6 primero.
    """
    return (
        b"# HELP "
        + _OLDEST_PENDING_METRIC
        + b" Antiguedad en segundos del trabajo OCR pendiente mas viejo.\n"
        + b"# TYPE "
        + _OLDEST_PENDING_METRIC
        + b" gauge\n"
        + _OLDEST_PENDING_METRIC
        + f" {age_seconds}\n".encode()
    )


@router.get("/metrics")
async def metrics(settings: Annotated[Settings, Depends(get_settings)]) -> Response:
    """Peticiones HTTP + salud de la cola OCR, en formato de texto Prometheus."""
    health = await ocr_queue_health(settings)
    recovery = await read_ocr_recovery_metrics()
    retention = await read_retention_metrics()
    if health is not None:
        ocr_queue_depth.set(health.depth)
    ocr_queue_backend_up.set(1 if health is not None else 0)
    pool = cast(QueuePool, get_engine().pool)
    db_pool_size_metric.set(pool.size())
    db_pool_checked_out_metric.set(pool.checkedout())
    db_pool_overflow_metric.set(max(pool.overflow(), 0))
    db_pool_capacity_metric.set(settings.db_pool_size + settings.db_max_overflow)
    if recovery is not None:
        pending_count.set(recovery.pending)
        ready_count.set(recovery.ready)
        for state, value in (
            ("pending", recovery.pending),
            ("processing", recovery.processing),
            ("abandoned", recovery.abandoned),
            ("failed", recovery.failed),
        ):
            ocr_documents.labels(state=state).set(value)
    if retention is not None:
        expired_pending_metric.set(retention.expired_pending_count)
        purge_storage_failures_metric.set(retention.purge_storage_failures)

    body = generate_latest(REGISTRY)
    if health is not None and health.oldest_pending_age_seconds is not None:
        body += _render_oldest_pending_line(health.oldest_pending_age_seconds)
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)

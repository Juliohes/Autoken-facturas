"""Encolado best-effort del job OCR desde la API (S2.3).

Tras una subida aceptada (S2.1), la API encola `run_ocr` para que el worker lo procese. Es
**best-effort**: si Redis/arq no está disponible, se registra el fallo y el fichero se queda en
`pending_ocr` (reintentable), pero la subida NO falla por ello. Así el intake no depende del worker.

Se capturan SOLO los fallos esperables de infraestructura del encolado (arq ausente, Redis caído,
timeout de conexión); un error de programación se deja propagar (no se enmascara). El fallo se
registra a nivel `error` con el `uploaded_file_id` para alertar de acumulación en `pending_ocr`.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from redis.exceptions import RedisError

from shared.config import get_settings

logger = structlog.get_logger(__name__)

# Nombre del task registrado en `jobs.worker.WorkerSettings.functions`.
_OCR_TASK = "run_ocr_task"
# S6.7 (benchmark real de variante x motor): task independiente del OCR principal, encolada al
# confirmar (C1), no al subir -- la verdad contra la que se puntúa solo existe tras confirmar.
_OCR_BENCHMARK_TASK = "run_ocr_benchmark_task"

# Fallos esperables del encolado (infra), que NO deben tumbar la subida: arq no instalado
# (ImportError), Redis inaccesible (`RedisError`/`OSError`) o timeout de conexión. Un error de
# programación (TypeError, etc.) NO está aquí: se deja propagar para no enmascararlo.
_ENQUEUE_INFRA_ERRORS = (ImportError, RedisError, OSError, asyncio.TimeoutError)


async def _enqueue(
    task_name: str,
    log_event: str,
    tenant_id: str | UUID,
    company_id: str | UUID,
    uploaded_file_id: str | UUID,
) -> None:
    """Encola `task_name(tenant_id, company_id, uploaded_file_id)` en la cola del worker
    (best-effort): crea el pool, encola, cierra el pool. Compartido por `enqueue_ocr`/
    `enqueue_ocr_benchmark` (2026-08-11, S6.7 auditoría, hallazgo de SOLID/DRY -- ambas funciones
    tenían el mismo cuerpo, solo cambiaba el nombre del task y el evento de log del fallo).

    Un fallo de infraestructura (Redis caído, arq ausente) se registra a nivel `error` con
    `log_event` y se traga: nunca se propaga al llamador.
    """
    settings = get_settings()
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            await pool.enqueue_job(
                task_name,
                str(tenant_id),
                str(company_id),
                str(uploaded_file_id),
                _queue_name=settings.ocr_queue_name,
            )
        finally:
            await pool.aclose()
    except _ENQUEUE_INFRA_ERRORS as exc:  # best-effort: el llamador no depende del worker
        logger.error(log_event, uploaded_file_id=str(uploaded_file_id), error=str(exc))


async def enqueue_ocr(
    tenant_id: str | UUID, company_id: str | UUID, uploaded_file_id: str | UUID
) -> None:
    """Encola `run_ocr(tenant_id, company_id, file_id)` en la cola del worker (best-effort).

    Un fallo de infraestructura (Redis caído, arq ausente) se registra a nivel `error` y se traga:
    la subida ya está persistida y el fichero se reprocesará; nunca se propaga al flujo de intake.
    """
    await _enqueue(_OCR_TASK, "ocr.enqueue_failed", tenant_id, company_id, uploaded_file_id)


async def enqueue_ocr_benchmark(
    tenant_id: str | UUID, company_id: str | UUID, uploaded_file_id: str | UUID
) -> None:
    """Encola `run_ocr_benchmark_task(tenant_id, company_id, file_id)` (S6.7, C1), best-effort.

    Mismo criterio que `enqueue_ocr`: un fallo de infraestructura del encolado (Redis caído, arq
    ausente) se registra y se traga -- confirmar una factura NUNCA depende del worker de benchmark.
    """
    await _enqueue(
        _OCR_BENCHMARK_TASK, "ocr_benchmark.enqueue_failed", tenant_id, company_id, uploaded_file_id
    )

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

# Fallos esperables del encolado (infra), que NO deben tumbar la subida: arq no instalado
# (ImportError), Redis inaccesible (`RedisError`/`OSError`) o timeout de conexión. Un error de
# programación (TypeError, etc.) NO está aquí: se deja propagar para no enmascararlo.
_ENQUEUE_INFRA_ERRORS = (ImportError, RedisError, OSError, asyncio.TimeoutError)


async def enqueue_ocr(
    tenant_id: str | UUID, company_id: str | UUID, uploaded_file_id: str | UUID
) -> None:
    """Encola `run_ocr(tenant_id, company_id, file_id)` en la cola del worker (best-effort).

    Un fallo de infraestructura (Redis caído, arq ausente) se registra a nivel `error` y se traga:
    la subida ya está persistida y el fichero se reprocesará; nunca se propaga al flujo de intake.
    """
    settings = get_settings()
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            await pool.enqueue_job(
                _OCR_TASK,
                str(tenant_id),
                str(company_id),
                str(uploaded_file_id),
                _queue_name=settings.ocr_queue_name,
            )
        finally:
            await pool.aclose()
    except _ENQUEUE_INFRA_ERRORS as exc:  # best-effort: el intake no depende del worker
        logger.error("ocr.enqueue_failed", uploaded_file_id=str(uploaded_file_id), error=str(exc))

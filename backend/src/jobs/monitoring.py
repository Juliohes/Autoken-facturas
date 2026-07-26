"""Salud de la cola OCR para observabilidad (S5.6): cuántos trabajos hay pendientes y desde cuándo
espera el más viejo.

Usa la API pública de arq (`ArqRedis.queued_jobs()`) en vez de reconstruir a mano las claves de
Redis que arq usa por dentro (spec §4): si arq cambia su representación interna, esta lectura no se
rompe en silencio devolviendo un número inventado.

Import perezoso de `arq` (mismo criterio que `jobs.queue.enqueue_ocr`, S2.3): si no está instalado
o Redis no responde, se trata como infraestructura caída, no como un error de programación —
`/metrics` sigue sirviendo el resto de métricas (spec §5).

Cacheada con un TTL corto (auditoría de seguridad): `GET /metrics` es público (spec §4, protegido a
nivel de red, no de aplicación) y cada lectura real abre y cierra un pool de Redis + trae TODOS los
trabajos pendientes a memoria (spec §5) — sin caché, una ráfaga de peticiones (aunque fuera
accidental, o si la protección de red fallara) se traduciría 1:1 en ese coste. El TTL es menor que
el intervalo de scrape de Prometheus (`infrastructure/prometheus/prometheus.yml`, 15s), así que un
scrape real siempre ve un dato fresco; solo las peticiones de más dentro de esa ventana reutilizan
el mismo resultado.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic

from redis.exceptions import RedisError

from shared.config import Settings

# Misma tupla que `jobs.queue._ENQUEUE_INFRA_ERRORS`: fallos esperables de infraestructura, nunca
# de programación. `asyncio.TimeoutError` es alias de `TimeoutError` (subclase de `OSError`) desde
# Python 3.11, así que ya estaría cubierta por `OSError` solo — se deja explícita para que ambas
# tuplas se lean como el mismo criterio, no dos variantes sutilmente distintas.
_QUEUE_HEALTH_INFRA_ERRORS = (ImportError, RedisError, OSError, asyncio.TimeoutError)
_CACHE_TTL_SECONDS = 10.0


@dataclass(frozen=True)
class OcrQueueHealth:
    """`depth`: trabajos pendientes. `oldest_pending_age_seconds`: `None` si la cola está vacía."""

    depth: int
    oldest_pending_age_seconds: float | None


_cache: tuple[float, OcrQueueHealth | None] | None = None


def reset_cache() -> None:
    """Descarta el valor cacheado (seam de test: cada caso necesita ver el estado real de SU
    cola, no el de una lectura de un caso anterior dentro del mismo TTL)."""
    global _cache
    _cache = None


async def ocr_queue_health(settings: Settings) -> OcrQueueHealth | None:
    """Consulta la cola OCR real (con caché de `_CACHE_TTL_SECONDS`); `None` si la infraestructura
    (arq/Redis) no está disponible."""
    global _cache
    now = monotonic()
    if _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
        return _cache[1]

    health = await _fetch_ocr_queue_health(settings)
    _cache = (now, health)
    return health


async def _fetch_ocr_queue_health(settings: Settings) -> OcrQueueHealth | None:
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        try:
            jobs = await pool.queued_jobs(queue_name=settings.ocr_queue_name)
        finally:
            await pool.aclose()
    except _QUEUE_HEALTH_INFRA_ERRORS:
        return None

    if not jobs:
        return OcrQueueHealth(depth=0, oldest_pending_age_seconds=None)

    oldest = min(job.enqueue_time for job in jobs)
    age_seconds = (datetime.now(UTC) - oldest).total_seconds()
    return OcrQueueHealth(depth=len(jobs), oldest_pending_age_seconds=max(age_seconds, 0.0))

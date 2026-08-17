"""Smoke test del cableado del worker arq (S2.3): caza incompatibilidades arq/redis en runtime.

`arq` declara `redis<6` pero la app corre con redis 8 (se instala con `--no-deps`, ver Dockerfile).
Ese "opera con redis 8" no es un supuesto: se VERIFICA aquí, encolando y consumiendo un job trivial
contra el Redis de test. Además comprueba que `WorkerSettings` expone lo que arq lee (functions,
on_startup del guard ADR-0014, queue_name, redis_settings). El comportamiento del OCR se prueba
aparte invocando `jobs.ocr.run_ocr` (test_ocr_worker.py); aquí solo el cableado del runtime.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from uuid import uuid4


async def _smoke_probe(ctx: dict[str, Any], key: str) -> None:
    """Task trivial de arq: escribe en Redis desde dentro del worker (observable tras consumir).

    A nivel de módulo a propósito: arq registra la función por su `__qualname__`, que para una
    función anidada llevaría `<locals>` y no casaría con el nombre encolado. En el módulo, el nombre
    registrado es `_smoke_probe` y coincide con el `enqueue_job("_smoke_probe", ...)`.
    """
    await ctx["redis"].set(key, b"ok")


async def test_worker_settings_estan_cableados() -> None:
    """`WorkerSettings` expone lo que arq lee: task registrado, guard de arranque, cola y Redis."""
    from jobs.worker import WorkerSettings, run_benchmark_batch_task, run_ocr_task, startup

    # S6.13 envuelve `run_ocr_task` en `func(...)` (timeout inferior al lease del claim, un único
    # intento automático): ya no es el objeto función pelado dentro de `functions`.
    ocr = next(
        item for item in WorkerSettings.functions if getattr(item, "name", None) == "run_ocr_task"
    )
    assert ocr.coroutine is run_ocr_task
    assert ocr.max_tries == 1
    assert WorkerSettings.on_startup is startup  # guard ADR-0014 en el arranque del worker
    assert WorkerSettings.queue_name
    assert WorkerSettings.redis_settings is not None
    batch = next(
        item
        for item in WorkerSettings.functions
        if getattr(item, "name", None) == "run_benchmark_batch_task"
    )
    assert batch.coroutine is run_benchmark_batch_task
    assert batch.timeout_s == 4 * 60 * 60
    assert batch.max_tries == 1


async def test_arq_encola_y_consume_contra_redis() -> None:
    """Encola un job trivial y lo consume con un worker arq en burst: verifica arq+redis runtime."""
    import pytest

    pytest.importorskip("arq")  # en CI (sin el extra `worker`) arq no está: se salta el smoke
    from arq import create_pool
    from arq.connections import RedisSettings
    from arq.worker import Worker

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/15")
    settings = RedisSettings.from_dsn(redis_url)
    # Cola y marca únicas: aisladas de la cola real del OCR y de otras claves de test en /15.
    queue = f"arq:smoke:{uuid4()}"
    marker = f"smoke:{uuid4()}"

    pool = await create_pool(settings)
    try:
        job = await pool.enqueue_job("_smoke_probe", marker, _queue_name=queue)
        assert job is not None  # arq devolvió un handle -> el encolado funcionó
        worker = Worker(
            functions=[_smoke_probe],
            redis_settings=settings,
            queue_name=queue,
            burst=True,  # procesa lo encolado y termina (no bucle infinito)
            poll_delay=0.0,
            handle_signals=False,  # pytest no corre en el hilo principal con handlers de señal
        )
        try:
            await asyncio.wait_for(worker.async_run(), timeout=15)
        finally:
            await worker.close()
        assert await pool.get(marker) == b"ok"  # el job se consumió y ejecutó
    finally:
        await pool.delete(marker)
        await pool.aclose()

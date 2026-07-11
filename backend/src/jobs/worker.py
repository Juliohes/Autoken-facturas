"""Configuración del worker arq (S2.3): registra `run_ocr` como task y conecta Redis.

Punto de entrada del proceso worker (`arq jobs.worker.WorkerSettings`). Comparte Postgres/MinIO con
la API por configuración (mismas env vars). El comportamiento del OCR se prueba invocando
`jobs.ocr.run_ocr` directamente; aquí solo se cablea el runtime de arq (verificado por el smoke test
`tests/test_ocr_worker_wiring.py`, no un arq real en CI).

Guardarraíl ADR-0014: al arrancar, el worker comprueba que su rol de conexión NO puede saltarse la
RLS (igual que el lifespan de la API en `main.py`). El worker escribe fijando el contexto de tenant
desde un mensaje encolado, así que ese invariante es tan crítico como en la API (fail-loud).
"""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from jobs.ocr import run_ocr
from shared.config import get_settings
from shared.db import get_engine
from shared.db_security import assert_runtime_role_cannot_bypass_rls

# Configuración leída UNA vez (no una llamada por atributo): cola y conexión Redis del worker.
_settings = get_settings()


async def run_ocr_task(
    ctx: dict[str, Any], tenant_id: str, company_id: str, uploaded_file_id: str
) -> None:
    """Task de arq: adapta la firma `(ctx, *args)` de arq al job de dominio `run_ocr`.

    `ctx` es el contexto del worker (no se usa: el job abre su propia sesión con contexto tenant).
    El extractor va a `None` -> el worker usa el motor real por defecto (gemini-3-flash).
    """
    await run_ocr(tenant_id, company_id, uploaded_file_id)


async def startup(ctx: dict[str, Any]) -> None:
    """Arranque del worker: aborta (fail-loud) si el rol de conexión puede eludir RLS (ADR-0014)."""
    await assert_runtime_role_cannot_bypass_rls(get_engine())


class WorkerSettings:
    """Ajustes que arq lee para arrancar el worker (`arq jobs.worker.WorkerSettings`)."""

    functions = [run_ocr_task]
    on_startup = startup
    queue_name = _settings.ocr_queue_name
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)

"""Lote retroactivo del benchmark real, panel de plataforma (S6.7 Área C, spec
docs/specs/S6.7-benchmark-real-motor-variante.md §0.5, C10-C17).

Dos piezas separadas a propósito:

- `run_benchmark_batch`: el motor TESTABLE, sin ningún fallback a motores reales (`extractors` es
  OBLIGATORIO, mismo criterio ya auditado que `ocr.benchmark.run_benchmark`/
  `jobs.ocr_ranking.run_ocr_ranking` -- ver sus docstrings para el incidente real de coste de S4.8
  que este patrón evita). Procesa `candidates` EN SECUENCIA (C15, un `for` simple, nunca
  `asyncio.gather` sobre documentos -- eso solo ocurre DENTRO de `ocr.benchmark.run_benchmark`, por
  motor dentro de una variante, C3). Reutiliza `jobs.ocr_benchmark._run_for_invoice` (el flujo de
  UNA factura, que SÍ puede lanzar) en vez de reimplementar "leer verdad + descargar + benchmark"
  una tercera vez.
- `run_benchmark_batch_task`: la task de arq, ÚNICO punto de producción legítimo que construye los
  4 candidatos R-032 desde `.env` para el lote retroactivo (mismo criterio que
  `jobs.ocr_benchmark.run_ocr_benchmark_task`). Toma el `pg_advisory_lock` real (C12, primer uso de
  este mecanismo en el proyecto) sobre una conexión `asyncpg` RAW dedicada -- nunca a través del
  pool normal de la app (agotaría el pool durante minutos, mismo tipo de incidente ya corregido en
  S5.5) -- mantenida abierta durante TODO el lote (el candado de sesión de Postgres exige la MISMA
  conexión para tomar y soltar). El candado es defensa en profundidad: el 409 del endpoint
  (`platform_admin.benchmark_batch_service.start_backfill`) ya debería evitar la carrera en el 99%
  de los casos, pero aquí se demuestra el mecanismo real contra Postgres (C12).

Progreso persistido en `ocr_benchmark_batch_runs` (migración 0030, sin RLS -- tabla de operación de
plataforma): `completed`/`failed_count` se actualizan en un `finally` POR CANDIDATO (C13, la barra
nunca se queda clavada aunque un documento falle), con una sesión/conexión Postgres normal (no hace
falta que sea la misma del candado). Si algo revienta FUERA del bucle por candidato (p. ej. el
propio descubrimiento de candidatos), la fila se marca `failed` en vez de quedarse `running` para
siempre -- defensa contra que un fallo de infraestructura deje el candado lógicamente "atascado" en
la tabla (el `pg_advisory_lock` en sí SIEMPRE se libera al cerrar la conexión, incluso si el proceso
muere; esto protege el ESTADO visible en el panel, no el candado).
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from sqlalchemy import text

from jobs.ocr_benchmark import _run_for_invoice
from ocr.extraction import InvoiceExtractor
from ocr.ranking_engines import build_named_benchmark_extractors
from platform_admin import benchmark_batch_repository
from shared.config import Settings, get_settings
from shared.db import platform_session
from shared.pg_dsn import to_libpq_dsn

logger = structlog.get_logger(__name__)

__all__ = ["BATCH_LOCK_KEY", "run_benchmark_batch", "run_benchmark_batch_task"]

# Clave fija del `pg_advisory_lock` del lote retroactivo del benchmark (S6.7 Área C, C12) -- primer
# uso de este mecanismo en el proyecto. Entero arbitrario de 63 bits (cabe en `bigint`), elegido a
# mano y documentado aquí para que nunca se reutilice por error en otro candado futuro del proyecto.
BATCH_LOCK_KEY = 892_374_651_029_384


async def run_benchmark_batch(
    batch_run_id: str,
    *,
    candidates: list[tuple[str, str, str]],
    extractors: list[tuple[str, InvoiceExtractor]],
    rate_limit_seconds: float = 1.0,
) -> None:
    """Procesa `candidates` (tenant_id, company_id, uploaded_file_id) EN SECUENCIA (C15), un
    documento detrás de otro -- nunca todos a la vez. Un fallo real de UN documento (C2/C13) nunca
    aborta el resto: se aísla con su propio `try/except`, y `completed`/`failed_count` avanzan en un
    `finally`, tanto si acabó bien como si falló. Pausa `rate_limit_seconds` entre documentos (spec
    §5.2), salvo tras el último. Al terminar todos, marca el lote `done`.
    """
    last_index = len(candidates) - 1
    for index, (tenant_id, company_id, uploaded_file_id) in enumerate(candidates):
        failed = False
        try:
            await _run_for_invoice(
                UUID(tenant_id),
                UUID(company_id),
                UUID(uploaded_file_id),
                extractors=extractors,
            )
        except Exception:  # noqa: BLE001  (aislamiento por documento, C2/C13)
            failed = True
            logger.error(
                "benchmark_batch.candidate_failed",
                batch_run_id=batch_run_id,
                uploaded_file_id=uploaded_file_id,
            )
        finally:
            await _advance_progress(batch_run_id, failed=failed)

        if index != last_index and rate_limit_seconds > 0:
            await asyncio.sleep(rate_limit_seconds)

    await _mark_done(batch_run_id)


async def _advance_progress(batch_run_id: str, *, failed: bool) -> None:
    """Avanza `completed`/`failed_count` vía `advance_batch_run_progress` (migración 0031,
    `SECURITY DEFINER`) -- el rol runtime ya no tiene acceso directo a la tabla (S6.7 auditoría
    2026-08-11, hallazgo de coherencia con `platform_settings`)."""
    async with platform_session() as session:
        await session.execute(
            text("SELECT advance_batch_run_progress(:id, :failed)"),
            {"id": batch_run_id, "failed": failed},
        )


async def _mark_done(batch_run_id: str) -> None:
    async with platform_session() as session:
        await session.execute(text("SELECT finish_batch_run(:id, 'done')"), {"id": batch_run_id})


async def _mark_failed(batch_run_id: str) -> None:
    """Solo si sigue `running` (garantizado dentro de `finish_batch_run`, migración 0031): si el
    bucle por candidato ya llegó a marcarlo `done` antes de que algo reventara en la limpieza, no lo
    pisa hacia atrás."""
    async with platform_session() as session:
        await session.execute(text("SELECT finish_batch_run(:id, 'failed')"), {"id": batch_run_id})


async def _discover_and_run(batch_run_id: str, settings: Settings) -> None:
    """Descubre los candidatos reales de ESTE lote (el `total` ya fijado por el endpoint, spec C10)
    y construye los motores reales UNA vez -- único punto de producción legítimo para el lote
    retroactivo (ver docstring del módulo)."""
    async with platform_session() as session:
        candidates = await benchmark_batch_repository.list_candidates(session, batch_run_id)

    extractors = build_named_benchmark_extractors(settings)
    await run_benchmark_batch(batch_run_id, candidates=candidates, extractors=extractors)


async def run_benchmark_batch_task(ctx: dict[str, Any], batch_run_id: str) -> None:
    """Task de arq del lote retroactivo (C10-C17). `ctx` no se usa (mismo patrón que el resto de
    tasks de `jobs`).

    Toma el `pg_advisory_lock` real (C12) sobre una conexión `asyncpg` RAW dedicada, mantenida
    abierta durante todo el lote -- el candado de sesión de Postgres exige la MISMA conexión para
    tomar y soltar, así que nunca pasa por el pool normal de SQLAlchemy.

    Garantía real (S6.7 auditoría 2026-08-11, hallazgo ALTO): CUALQUIER fallo en este camino --
    conectar a Postgres, tomar el candado, o `_discover_and_run` -- deja la fila marcada `failed`,
    nunca `running` para siempre. Antes, el `try/except -> _mark_failed` solo envolvía
    `_discover_and_run`: si `asyncpg.connect` o el `pg_advisory_lock` fallaban (Postgres
    inalcanzable justo en ese instante), la excepción escapaba SIN pasar por `_mark_failed` -- la
    fila quedaba `running` para siempre, y cualquier `POST` futuro chocaba con el 409 de "ya hay un
    lote corriendo" contra un lote que nunca iba a avanzar, sin ningún mecanismo de recuperación.
    `_mark_failed` usa su propia sesión SQLAlchemy (`platform_session`), independiente de esta
    conexión `asyncpg` -- puede marcar la fila incluso si esa conexión nunca llegó a establecerse.
    El candado `pg_advisory_lock` en sí SIEMPRE se libera al cerrar la conexión, incluso si el
    proceso muere a medias; esto protege el ESTADO visible en el panel, no el candado.
    """
    settings = get_settings()
    try:
        conn = await asyncpg.connect(to_libpq_dsn(settings.database_url))
    except Exception:  # noqa: BLE001  (nunca deja la fila en 'running' para siempre)
        logger.error("benchmark_batch.connect_failed", batch_run_id=batch_run_id)
        await _mark_failed(batch_run_id)
        return
    try:
        try:
            await conn.execute("SELECT pg_advisory_lock($1)", BATCH_LOCK_KEY)
        except Exception:  # noqa: BLE001  (nunca deja la fila en 'running' para siempre)
            logger.error("benchmark_batch.lock_failed", batch_run_id=batch_run_id)
            await _mark_failed(batch_run_id)
            return
        try:
            # ARQ puede redeliver un mensaje tras una caída. Una vez liberado el candado, nunca se
            # vuelve a pagar un lote ya cerrado ni se infla su progreso.
            async with platform_session() as session:
                batch = await benchmark_batch_repository.get_by_id(session, batch_run_id)
            if batch is None or batch.status != "running":
                return
            if batch.completed >= batch.total:
                await _mark_done(batch_run_id)
                return
            await _discover_and_run(batch_run_id, settings)
        except Exception:  # noqa: BLE001  (nunca deja la fila en 'running' para siempre)
            logger.error("benchmark_batch.task_failed", batch_run_id=batch_run_id)
            await _mark_failed(batch_run_id)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", BATCH_LOCK_KEY)
    finally:
        await conn.close()

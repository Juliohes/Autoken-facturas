"""Lógica de dominio del panel de lote retroactivo del benchmark real (S6.7 Área C, spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C10/C11/C14/C16).

`start_backfill` es la ÚNICA responsable de aplicar el tope duro de 30 (C14), de comprobar el
interruptor (spec §4, "solo corre bajo el interruptor explícito") y de decidir si ya hay un lote
corriendo (C11): si lo hay, devuelve `started=False` + el progreso de ESE lote (nunca crea uno
nuevo, nunca encola un segundo trabajo). El candado real (`pg_advisory_lock`, C12) es una defensa
en profundidad tomada por el worker (`jobs.ocr_benchmark_batch`), no por este servicio -- el
`SELECT ... WHERE status = 'running'` de aquí puede, en teoría, perder una carrera muy estrecha
entre dos peticiones simultáneas; el candado del worker es quien de verdad garantiza que solo un
lote procesa a la vez pase lo que pase en esta capa (spec §0.5).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from jobs import queue
from ocr.benchmark_backfill_repository import list_benchmark_candidates
from platform_admin import benchmark_batch_repository, settings_repository
from platform_admin.benchmark_batch_repository import BatchRun

__all__ = ["HARD_LIMIT", "OcrExperimentDisabled", "get_status", "start_backfill"]

# Tope duro del lote (C14, spec §5.2): como mucho 30 facturas por invocación, sin importar lo que
# se pida -- evita un lote descontrolado que dispare miles de llamadas de pago por un valor mal
# tecleado.
HARD_LIMIT = 30


class OcrExperimentDisabled(Exception):
    """El interruptor `platform_settings.ocr_experiment_enabled` está apagado (S6.7 auditoría
    2026-08-11, hallazgo ALTO): antes, `start_backfill` insertaba la fila `running` y encolaba el
    trabajo sin mirarlo -- como `_run_for_invoice` sale en silencio con el interruptor apagado, el
    lote terminaba en `status='done'` sin haber llamado a ningún motor ni guardado ninguna
    combinación, sin ningún aviso de que el interruptor era la causa real (contradice spec §4). El
    router la traduce a 422 con un mensaje explícito -- nunca se llega a insertar fila ni a
    encolar nada."""


async def start_backfill(session: AsyncSession, *, limit: int) -> tuple[bool, BatchRun]:
    """Devuelve `(iniciado, lote)`. `iniciado=False` cuando ya había un lote `running`: `lote` es
    el YA EN CURSO (nunca uno nuevo), para que el llamador responda 409 con su progreso (C11).

    Lanza `OcrExperimentDisabled` si el interruptor está apagado, ANTES de contar candidatos,
    insertar la fila o encolar nada (comprobado primero, incluso antes de mirar si ya hay un lote
    `running`: apagado significa que no se inicia nada, pase lo que pase)."""
    settings_row = await settings_repository.get_settings(session)
    if not settings_row.ocr_experiment_enabled:
        raise OcrExperimentDisabled()

    running = await benchmark_batch_repository.get_running(session)
    if running is not None:
        return False, running

    effective_limit = min(limit, HARD_LIMIT)
    candidates = await list_benchmark_candidates(session, effective_limit)
    total = len(candidates)

    batch = await benchmark_batch_repository.insert_running(session, total=total)
    # Best-effort (mismo criterio que `enqueue_ocr`/`enqueue_ocr_benchmark`): un fallo de
    # infraestructura del encolado no debe impedir que la fila `running` quede registrada -- el
    # candado/CLI puede relanzarse manualmente si el worker nunca llega a procesarla.
    await queue.enqueue_ocr_benchmark_batch(str(batch.id))
    return True, batch


async def get_status(session: AsyncSession) -> BatchRun | None:
    """El lote `running` si lo hay; si no, el más reciente ya terminado; `None` si nunca se lanzó
    ninguno (C16)."""
    running = await benchmark_batch_repository.get_running(session)
    if running is not None:
        return running
    return await benchmark_batch_repository.get_latest(session)

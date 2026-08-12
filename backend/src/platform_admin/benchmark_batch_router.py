"""Endpoints HTTP del panel de lote retroactivo del benchmark real (S6.7 Área C, spec
docs/specs/S6.7-benchmark-real-motor-variante.md §0.5, C10/C11/C14/C16):
`POST /api/v1/platform/benchmark/backfill` + `GET /api/v1/platform/benchmark/backfill/status`.

Capa HTTP fina: autentica y autoriza (`require_admin_tech`, exige `platform_admin` + el flag
`is_admin_tech`, comprobado fresco en cada petición, mismo criterio que el resto de
`platform_admin`) y delega en `benchmark_batch_service`. El endpoint SOLO encola el trabajo y
responde al instante (C10) -- el procesado real ocurre en el worker
(`jobs.ocr_benchmark_batch.run_benchmark_batch_task`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from identity.authz import require_admin_tech
from identity.dependencies import AdminTechAuthContext
from platform_admin import benchmark_batch_service
from platform_admin.benchmark_batch_repository import BatchRun
from platform_admin.benchmark_batch_service import OcrExperimentDisabled

router = APIRouter(prefix="/platform/benchmark/backfill", tags=["platform"])

AdminTech = Annotated[AdminTechAuthContext, Depends(require_admin_tech())]

_EXPERIMENT_DISABLED_DETAIL = (
    "El experimento OCR está apagado — actívalo en Ajustes antes de lanzar el lote retroactivo."
)


class BackfillIn(BaseModel):
    # `ge=1` (S6.7 auditoría 2026-08-11, hallazgo MEDIO): sin cota inferior, `limit=0`/negativo
    # llegaba tal cual a Postgres y `LIMIT 0`/negativo (`ocr_benchmark_candidates`) reventaba con un
    # 500 crudo en vez de un 422 claro de validación.
    limit: int = Field(ge=1)


class BatchStatusOut(BaseModel):
    status: str
    total: int
    completed: int
    failed_count: int


class BackfillStartedOut(BaseModel):
    iniciado: bool
    total: int


class BackfillConflictOut(BaseModel):
    batch: BatchStatusOut


class BackfillStatusOut(BaseModel):
    running: bool
    batch: BatchStatusOut | None


def _to_status_out(batch: BatchRun) -> BatchStatusOut:
    return BatchStatusOut(
        status=batch.status,
        total=batch.total,
        completed=batch.completed,
        failed_count=batch.failed_count,
    )


@router.post(
    "",
    status_code=200,
    response_model=BackfillStartedOut,
    responses={409: {"model": BackfillConflictOut}},
)
async def start_backfill(
    body: BackfillIn, identity: AdminTech
) -> BackfillStartedOut | JSONResponse:
    """C10: responde de inmediato, sin esperar a que termine ni una sola combinación. C11: si ya
    hay un lote `running`, responde 409 con su progreso (mismo patrón ya usado por
    `invoice_intake.router` para `duplicate_of`: `JSONResponse` con cuerpo estructurado propio,
    `response_model` fijado explícitamente para que FastAPI solo lo aplique al camino 200) -- el
    frontend se engancha a él, nunca lo trata como un error genérico. Interruptor apagado -> 422
    (S6.7 auditoría 2026-08-11, hallazgo ALTO): nunca se llega a insertar ni encolar nada."""
    try:
        started, batch = await benchmark_batch_service.start_backfill(
            identity.session, limit=body.limit
        )
    except OcrExperimentDisabled as exc:
        raise HTTPException(status_code=422, detail=_EXPERIMENT_DISABLED_DETAIL) from exc
    if not started:
        return JSONResponse(status_code=409, content={"batch": _to_status_out(batch).model_dump()})
    return BackfillStartedOut(iniciado=True, total=batch.total)


@router.get("/status")
async def get_backfill_status(identity: AdminTech) -> BackfillStatusOut:
    """C16: el lote `running` si lo hay; si no, el más reciente ya terminado; `None` si nunca se
    lanzó ninguno."""
    batch = await benchmark_batch_service.get_status(identity.session)
    if batch is None:
        return BackfillStatusOut(running=False, batch=None)
    return BackfillStatusOut(running=batch.status == "running", batch=_to_status_out(batch))

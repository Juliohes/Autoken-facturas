"""Endpoint HTTP del ranking agregado del benchmark real (S6.7 Área D, spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C18-C20):
`GET /api/v1/platform/benchmark/ranking`.

Sustituye a la vista principal del panel de ranking S4.8 (`ranking_router.py`, que NO se toca --
spec §6) por un agregado más útil: por grupo de campo (C18) y por combinación variant x engine
(C20). Capa HTTP fina: autentica y autoriza (`require_admin_tech`, mismo criterio que el resto de
`platform_admin`) y delega en `benchmark_ranking_service`. GET puro de solo lectura sobre datos ya
persistidos, sin ningún parámetro que dispare una llamada real a un proveedor de IA (C19).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from identity.authz import require_admin_tech
from identity.dependencies import AdminTechAuthContext
from platform_admin import benchmark_ranking_service

router = APIRouter(prefix="/platform/benchmark/ranking", tags=["platform"])

AdminTech = Annotated[AdminTechAuthContext, Depends(require_admin_tech())]


class FieldGroupRankingOut(BaseModel):
    field_group: str
    variant: str
    engine: str
    aciertos: int
    comparables: int
    ratio: float


class CombinationSummaryOut(BaseModel):
    variant: str
    engine: str
    executions: int
    errors: int
    aciertos: int
    comparables: int
    avg_duration_ms: float | None


class BenchmarkRankingOut(BaseModel):
    by_field_group: list[FieldGroupRankingOut]
    by_combination: list[CombinationSummaryOut]


@router.get("")
async def get_benchmark_ranking(identity: AdminTech) -> BenchmarkRankingOut:
    field_groups = await benchmark_ranking_service.get_benchmark_field_group_ranking(
        identity.session
    )
    combinations = await benchmark_ranking_service.get_benchmark_combination_summary(
        identity.session
    )
    return BenchmarkRankingOut(
        by_field_group=[
            FieldGroupRankingOut(
                field_group=row.field_group,
                variant=row.variant,
                engine=row.engine,
                aciertos=row.aciertos,
                comparables=row.comparables,
                ratio=row.ratio,
            )
            for row in field_groups
        ],
        by_combination=[
            CombinationSummaryOut(
                variant=row.variant,
                engine=row.engine,
                executions=row.executions,
                errors=row.errors,
                aciertos=row.aciertos,
                comparables=row.comparables,
                avg_duration_ms=row.avg_duration_ms,
            )
            for row in combinations
        ],
    )

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
    # `None` cuando `comparables == 0`: sin datos todavía, distinto de "0% de acierto real"
    # (auditoría S6.7, hallazgo MEDIO de SOLID).
    ratio: float | None


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


class BenchmarkMetricsSummaryOut(BaseModel):
    variant: str
    engine: str
    model: str | None
    executions: int
    errors: int
    field_exact_accuracy: float | None
    critical_field_accuracy: float | None
    all_critical_exact_rate: float | None
    tax_lines_accuracy: float | None
    arithmetic_valid_rate: float | None
    hallucination_cases: int
    p50_duration_ms: float | None
    p95_duration_ms: float | None
    pages: float | None
    api_cost_usd: str | None
    manual_corrections_per_invoice: float | None


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


@router.get("/metrics", response_model=list[BenchmarkMetricsSummaryOut])
async def get_benchmark_metrics(identity: AdminTech) -> list[BenchmarkMetricsSummaryOut]:
    """Informe R-032 de métricas comparables, sin ejecutar motores OCR."""
    rows = await benchmark_ranking_service.get_benchmark_metrics_summary(identity.session)
    return [BenchmarkMetricsSummaryOut.model_validate(row, from_attributes=True) for row in rows]

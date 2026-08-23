"""Acceso a datos del ranking agregado del benchmark real (S6.7 Área D, spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C18-C20): SQL de las dos funciones `SECURITY
DEFINER` de la migración 0032.

Mismo patrón que `ocr.ranking_repository.get_engine_summary` (S4.8): agrega A TRAVÉS de todos los
tenants para el panel admin-tech, así que se invoca desde `shared.db.platform_session()` (sin
contexto de tenant), nunca desde `tenant_session`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "CombinationSummary",
    "FieldGroupRanking",
    "BenchmarkMetricsSummary",
    "get_combination_summary",
    "get_field_group_ranking",
    "get_metrics_summary",
]


@dataclass(frozen=True)
class FieldGroupRanking:
    field_group: str
    variant: str
    engine: str
    aciertos: int
    comparables: int
    # `None` cuando `comparables == 0` (ningún dato comparable en este grupo/combinación) --
    # nunca `0.0`, que se confundiría con "0% de acierto real" (auditoría S6.7, hallazgo MEDIO
    # de SOLID: `ocr_benchmark_field_group_ranking()` ya no envuelve la división con `COALESCE`).
    ratio: float | None


@dataclass(frozen=True)
class CombinationSummary:
    variant: str
    engine: str
    executions: int
    errors: int
    aciertos: int
    comparables: int
    avg_duration_ms: float | None


@dataclass(frozen=True)
class BenchmarkMetricsSummary:
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


async def get_field_group_ranking(session: AsyncSession) -> list[FieldGroupRanking]:
    """Aciertos/comparables por (grupo de campo, variant, engine), C18."""
    rows = (
        await session.execute(
            text(
                "SELECT field_group, variant, engine, aciertos, comparables, ratio "
                "FROM ocr_benchmark_field_group_ranking()"
            )
        )
    ).all()
    return [
        FieldGroupRanking(
            field_group=row.field_group,
            variant=row.variant,
            engine=row.engine,
            aciertos=row.aciertos,
            comparables=row.comparables,
            ratio=row.ratio,
        )
        for row in rows
    ]


async def get_combination_summary(session: AsyncSession) -> list[CombinationSummary]:
    """Ejecuciones/errores/ratio/tiempo medio por (variant, engine), C20."""
    rows = (
        await session.execute(
            text(
                "SELECT variant, engine, executions, errors, aciertos, comparables, "
                "avg_duration_ms FROM ocr_benchmark_combination_summary()"
            )
        )
    ).all()
    return [
        CombinationSummary(
            variant=row.variant,
            engine=row.engine,
            executions=row.executions,
            errors=row.errors,
            aciertos=row.aciertos,
            comparables=row.comparables,
            avg_duration_ms=row.avg_duration_ms,
        )
        for row in rows
    ]


async def get_metrics_summary(session: AsyncSession) -> list[BenchmarkMetricsSummary]:
    """Devuelve las métricas comparables de R-032 por variante, motor y modelo."""
    rows = (
        await session.execute(
            text(
                "SELECT variant, engine, model, executions, errors, field_exact_accuracy, "
                "critical_field_accuracy, all_critical_exact_rate, tax_lines_accuracy, "
                "arithmetic_valid_rate, hallucination_cases, p50_duration_ms, p95_duration_ms, "
                "pages, api_cost_usd, manual_corrections_per_invoice "
                "FROM ocr_benchmark_r032_metrics_summary()"
            )
        )
    ).all()
    return [
        BenchmarkMetricsSummary(
            variant=row.variant,
            engine=row.engine,
            model=row.model,
            executions=row.executions,
            errors=row.errors,
            field_exact_accuracy=row.field_exact_accuracy,
            critical_field_accuracy=row.critical_field_accuracy,
            all_critical_exact_rate=row.all_critical_exact_rate,
            tax_lines_accuracy=row.tax_lines_accuracy,
            arithmetic_valid_rate=row.arithmetic_valid_rate,
            hallucination_cases=row.hallucination_cases,
            p50_duration_ms=row.p50_duration_ms,
            p95_duration_ms=row.p95_duration_ms,
            pages=row.pages,
            api_cost_usd=str(row.api_cost_usd) if row.api_cost_usd is not None else None,
            manual_corrections_per_invoice=row.manual_corrections_per_invoice,
        )
        for row in rows
    ]

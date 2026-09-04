"""Servicio del ranking agregado del benchmark real (S6.7 Área D): passthrough sobre
`ocr.benchmark_ranking_repository` (mismo patrón que `ranking_service`, S4.8).

Capa fina entre el router HTTP y el repositorio: sitio natural para una regla de negocio futura
sobre el agregado, sin acoplar el router al SQL.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ocr.benchmark_ranking_repository import (
    BenchmarkMetricsSummary,
    CombinationSummary,
    FieldGroupRanking,
    get_combination_summary,
    get_field_group_ranking,
    get_metrics_summary,
)

__all__ = [
    "get_benchmark_combination_summary",
    "get_benchmark_field_group_ranking",
    "get_benchmark_metrics_summary",
]


async def get_benchmark_field_group_ranking(session: AsyncSession) -> list[FieldGroupRanking]:
    return await get_field_group_ranking(session)


async def get_benchmark_combination_summary(session: AsyncSession) -> list[CombinationSummary]:
    return await get_combination_summary(session)


async def get_benchmark_metrics_summary(
    session: AsyncSession,
) -> list[BenchmarkMetricsSummary]:
    return await get_metrics_summary(session)

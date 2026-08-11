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
    "get_combination_summary",
    "get_field_group_ranking",
]


@dataclass(frozen=True)
class FieldGroupRanking:
    field_group: str
    variant: str
    engine: str
    aciertos: int
    comparables: int
    ratio: float


@dataclass(frozen=True)
class CombinationSummary:
    variant: str
    engine: str
    executions: int
    errors: int
    aciertos: int
    comparables: int
    avg_duration_ms: float | None


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

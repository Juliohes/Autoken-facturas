"""Acceso a datos del ranking multi-modelo (S4.8): SQL de `ocr_ranking_entries`.

`upsert_ranking_entry` sigue el mismo patrón que `ocr.comparison_repository` (S2.10): la sesión
llega ya abierta en el contexto de tenant (RLS de dos niveles); el `tenant_id` de la escritura sale
de `app.tenant_id` (nunca por parámetro); upsert por `(uploaded_file_id, engine)` (idempotencia por
motor).

`get_engine_summary` es distinto: agrega A TRAVÉS de todos los tenants para el panel admin-tech, así
que llama a la función `SECURITY DEFINER` `ocr_ranking_summary()` (migración 0019) en vez de hacer
un `SELECT` bajo RLS — igual que `ocr.backfill_repository.list_backfill_candidates` — y se invoca
desde `shared.db.platform_session()` (sin contexto de tenant), nunca desde `tenant_session`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = [
    "EngineRankingExample",
    "EngineRankingSummary",
    "RankingEntry",
    "get_engine_summary",
    "list_ranking_entries",
    "list_ranking_examples",
    "upsert_ranking_entry",
]

# Tope de ejemplos por motor del panel de plataforma (2026-08-09): una muestra concreta basta para
# diagnosticar cualitativamente, no hace falta paginar (mismo criterio que otras vistas admin-tech
# de solo diagnóstico, sin exigir un límite configurable por el cliente).
_EXAMPLES_LIMIT = 5

_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_UPSERT = text(
    f"INSERT INTO ocr_ranking_entries "
    f"(tenant_id, company_id, uploaded_file_id, engine, model, reading, score) "
    f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :uploaded_file_id, :engine, :model, "
    f" CAST(:reading AS jsonb), :score) "
    f"ON CONFLICT (uploaded_file_id, engine) DO UPDATE SET "
    f" model = EXCLUDED.model, reading = EXCLUDED.reading, score = EXCLUDED.score, "
    f" updated_at = now()"
)


@dataclass(frozen=True)
class EngineRankingSummary:
    engine: str
    invoices_read: int
    average_score: float
    first_place_count: int


@dataclass(frozen=True)
class EngineRankingExample:
    """Una lectura real de un motor concreto (2026-08-09, panel de plataforma: "ver ejemplos
    concretos, no solo números"), la más reciente primero. A través de todos los tenants, igual
    que `EngineRankingSummary` — mismo criterio de visibilidad admin-tech ya establecido."""

    uploaded_file_id: UUID
    model: str
    reading: dict[str, Any]
    score: int


@dataclass(frozen=True)
class RankingEntry:
    """Una fila de `ocr_ranking_entries` de UN fichero concreto (S6.2, laboratorio admin-tech,
    comparativa de modelos): a diferencia de `EngineRankingSummary` (agregado A TRAVÉS de todos los
    tenants para el panel de ranking, S4.8), esta es la lectura de un motor para una factura."""

    engine: str
    model: str
    reading: dict[str, Any]
    score: int


async def upsert_ranking_entry(
    session: AsyncSession,
    *,
    company_id: UUID,
    uploaded_file_id: UUID,
    engine: str,
    model: str,
    reading: dict[str, Any],
    score: int,
) -> None:
    """Inserta o reemplaza la entrada de este motor para este fichero (idempotente por motor)."""
    await session.execute(
        _UPSERT,
        {
            "company_id": str(company_id),
            "uploaded_file_id": str(uploaded_file_id),
            "engine": engine,
            "model": model,
            "reading": json.dumps(reading),
            "score": score,
        },
    )


async def list_ranking_entries(session: AsyncSession, uploaded_file_id: UUID) -> list[RankingEntry]:
    """Comparativa de motores de UN fichero, ordenada de mayor a menor puntuación (S6.2, laboratorio
    admin-tech, spec C12/C13). Sesión dentro de una `tenant_session` ya abierta (RLS de dos niveles,
    a diferencia de `get_engine_summary`, que agrega a través de todos los tenants sin RLS). Lista
    vacía si el experimento no estaba encendido cuando se procesó esa factura (nunca un error)."""
    rows = (
        await session.execute(
            text(
                "SELECT engine, model, reading, score FROM ocr_ranking_entries "
                "WHERE uploaded_file_id = :fid ORDER BY score DESC"
            ),
            {"fid": str(uploaded_file_id)},
        )
    ).all()
    return [
        RankingEntry(engine=row.engine, model=row.model, reading=dict(row.reading), score=row.score)
        for row in rows
    ]


async def list_ranking_examples(session: AsyncSession, engine: str) -> list[EngineRankingExample]:
    """Hasta `_EXAMPLES_LIMIT` lecturas reales de un motor concreto, la más reciente primero
    (2026-08-09); llamar desde `shared.db.platform_session` (sin tenant), mismo criterio que
    `get_engine_summary`. Motor sin ninguna lectura -> lista vacía, nunca un error."""
    rows = (
        await session.execute(
            text(
                "SELECT uploaded_file_id, model, reading, score FROM ocr_ranking_examples(:e, :l)"
            ),
            {"e": engine, "l": _EXAMPLES_LIMIT},
        )
    ).all()
    return [
        EngineRankingExample(
            uploaded_file_id=row.uploaded_file_id,
            model=row.model,
            reading=dict(row.reading),
            score=row.score,
        )
        for row in rows
    ]


async def get_engine_summary(session: AsyncSession) -> list[EngineRankingSummary]:
    """Ranking agregado por motor (C11); llamar desde `shared.db.platform_session` (sin tenant)."""
    rows = (
        await session.execute(
            text(
                "SELECT engine, invoices_read, average_score, first_place_count "
                "FROM ocr_ranking_summary()"
            )
        )
    ).all()
    return [
        EngineRankingSummary(
            engine=row.engine,
            invoices_read=row.invoices_read,
            average_score=row.average_score,
            first_place_count=row.first_place_count,
        )
        for row in rows
    ]

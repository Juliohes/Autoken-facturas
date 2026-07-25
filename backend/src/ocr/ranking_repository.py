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

__all__ = ["EngineRankingSummary", "get_engine_summary", "upsert_ranking_entry"]

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

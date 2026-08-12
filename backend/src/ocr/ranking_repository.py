"""Acceso a datos del ranking multi-modelo (S4.8): SQL de `ocr_ranking_entries`.

`upsert_ranking_entry` sigue el mismo patrón que `ocr.comparison_repository` (S2.10): la sesión
llega ya abierta en el contexto de tenant (RLS de dos niveles); el `tenant_id` de la escritura sale
de `app.tenant_id` (nunca por parámetro); upsert por `(uploaded_file_id, engine)` (idempotencia por
motor).

`get_engine_summary` es distinto: agrega A TRAVÉS de todos los tenants para el panel admin-tech, así
que llama a la función `SECURITY DEFINER` `ocr_ranking_summary()` (migración 0019) en vez de hacer
un `SELECT` bajo RLS — igual que `ocr.backfill_repository.list_backfill_candidates` — y se invoca
desde `shared.db.platform_session()` (sin contexto de tenant), nunca desde `tenant_session`.

`counterparty_tax_id`/`counterparty_name` (S6.7 C24, mismo patrón ADR-0018 que
`ocr.comparison_repository`/`ocr.benchmark_repository`) viajan cifrados con la clave del tenant en
dos columnas `bytea` dedicadas. `encryption_key` llega ya derivada (el repositorio nunca deriva
claves, lo hace el llamador, `jobs.ocr_ranking`). Antes de serializar `reading` a JSONB se quitan
esas dos claves del dict: nunca deben quedar duplicadas en claro junto a la versión ya cifrada.
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
    "get_engine_summary",
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
    f"(tenant_id, company_id, uploaded_file_id, engine, model, reading, "
    f" counterparty_tax_id, counterparty_name, score) "
    f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :uploaded_file_id, :engine, :model, "
    f" CAST(:reading AS jsonb), pgp_sym_encrypt(:counterparty_tax_id, :key), "
    f" pgp_sym_encrypt(:counterparty_name, :key), :score) "
    f"ON CONFLICT (uploaded_file_id, engine) DO UPDATE SET "
    f" model = EXCLUDED.model, reading = EXCLUDED.reading, "
    f" counterparty_tax_id = EXCLUDED.counterparty_tax_id, "
    f" counterparty_name = EXCLUDED.counterparty_name, "
    f" score = EXCLUDED.score, "
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


async def upsert_ranking_entry(
    session: AsyncSession,
    *,
    company_id: UUID,
    uploaded_file_id: UUID,
    engine: str,
    model: str,
    reading: dict[str, Any],
    score: int,
    encryption_key: str,
) -> None:
    """Inserta o reemplaza la entrada de este motor para este fichero (idempotente por motor)."""
    stripped_reading = dict(reading)
    counterparty_tax_id = stripped_reading.pop("counterparty_tax_id", None)
    counterparty_name = stripped_reading.pop("counterparty_name", None)
    await session.execute(
        _UPSERT,
        {
            "company_id": str(company_id),
            "uploaded_file_id": str(uploaded_file_id),
            "engine": engine,
            "model": model,
            "reading": json.dumps(stripped_reading),
            "counterparty_tax_id": counterparty_tax_id,
            "counterparty_name": counterparty_name,
            "score": score,
            "key": encryption_key,
        },
    )


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

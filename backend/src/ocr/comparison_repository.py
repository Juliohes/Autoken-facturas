"""Acceso a datos de la comparativa original-vs-realzada (S2.10): SQL de `ocr_comparison_runs`.

Mismo patrón que `ocr.repository` (S2.3): la sesión llega ya abierta en el contexto de tenant (RLS
de dos niveles); el `tenant_id` de la escritura sale de `app.tenant_id` (nunca por parámetro), y el
upsert por `uploaded_file_id` (UNIQUE) garantiza una comparativa vigente por fichero (idempotencia).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_UPSERT = text(
    f"INSERT INTO ocr_comparison_runs "
    f"(tenant_id, company_id, uploaded_file_id, original_reading, enhanced_reading, "
    f" original_score, enhanced_score, winner, engine, model) "
    f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :uploaded_file_id, "
    f" CAST(:original_reading AS jsonb), CAST(:enhanced_reading AS jsonb), "
    f" :original_score, :enhanced_score, :winner, :engine, :model) "
    f"ON CONFLICT (uploaded_file_id) DO UPDATE SET "
    f" original_reading = EXCLUDED.original_reading, enhanced_reading = EXCLUDED.enhanced_reading, "
    f" original_score = EXCLUDED.original_score, enhanced_score = EXCLUDED.enhanced_score, "
    f" winner = EXCLUDED.winner, engine = EXCLUDED.engine, model = EXCLUDED.model, "
    f" updated_at = now()"
)


async def upsert_comparison_run(
    session: AsyncSession,
    *,
    company_id: UUID,
    uploaded_file_id: UUID,
    original_reading: dict[str, Any],
    enhanced_reading: dict[str, Any],
    original_score: int,
    enhanced_score: int,
    winner: str,
    engine: str,
    model: str,
) -> None:
    """Inserta o reemplaza la comparativa del fichero en el tenant del contexto (idempotente)."""
    await session.execute(
        _UPSERT,
        {
            "company_id": str(company_id),
            "uploaded_file_id": str(uploaded_file_id),
            "original_reading": json.dumps(original_reading),
            "enhanced_reading": json.dumps(enhanced_reading),
            "original_score": original_score,
            "enhanced_score": enhanced_score,
            "winner": winner,
            "engine": engine,
            "model": model,
        },
    )

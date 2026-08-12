"""Acceso a datos de la comparativa original-vs-realzada (S2.10): SQL de `ocr_comparison_runs`.

Mismo patrón que `ocr.repository` (S2.3): la sesión llega ya abierta en el contexto de tenant (RLS
de dos niveles); el `tenant_id` de la escritura sale de `app.tenant_id` (nunca por parámetro), y el
upsert por `uploaded_file_id` (UNIQUE) garantiza una comparativa vigente por fichero (idempotencia).

`counterparty_tax_id`/`counterparty_name` (S6.7 C24, mismo patrón ADR-0018 que
`ocr.benchmark_repository`) viajan cifrados con la clave del tenant en 4 columnas `bytea` dedicadas
-- una pareja por lectura (`original_*`/`enhanced_*`, pueden diferir entre la lectura original y la
realzada). `encryption_key` llega ya derivada (el repositorio nunca deriva claves, lo hace el
llamador, `jobs.ocr`, con `shared.encryption.tenant_encryption_key`). Antes de serializar
`original_reading`/`enhanced_reading` a JSONB, se quitan esas dos claves de CADA dict: nunca deben
quedar duplicadas en claro junto a la versión ya cifrada.
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
    f" original_counterparty_tax_id, original_counterparty_name, "
    f" enhanced_counterparty_tax_id, enhanced_counterparty_name, "
    f" original_score, enhanced_score, winner, engine, model) "
    f"VALUES ({_TENANT_FROM_CONTEXT}, :company_id, :uploaded_file_id, "
    f" CAST(:original_reading AS jsonb), CAST(:enhanced_reading AS jsonb), "
    f" pgp_sym_encrypt(:original_counterparty_tax_id, :key), "
    f" pgp_sym_encrypt(:original_counterparty_name, :key), "
    f" pgp_sym_encrypt(:enhanced_counterparty_tax_id, :key), "
    f" pgp_sym_encrypt(:enhanced_counterparty_name, :key), "
    f" :original_score, :enhanced_score, :winner, :engine, :model) "
    f"ON CONFLICT (uploaded_file_id) DO UPDATE SET "
    f" original_reading = EXCLUDED.original_reading, enhanced_reading = EXCLUDED.enhanced_reading, "
    f" original_counterparty_tax_id = EXCLUDED.original_counterparty_tax_id, "
    f" original_counterparty_name = EXCLUDED.original_counterparty_name, "
    f" enhanced_counterparty_tax_id = EXCLUDED.enhanced_counterparty_tax_id, "
    f" enhanced_counterparty_name = EXCLUDED.enhanced_counterparty_name, "
    f" original_score = EXCLUDED.original_score, enhanced_score = EXCLUDED.enhanced_score, "
    f" winner = EXCLUDED.winner, engine = EXCLUDED.engine, model = EXCLUDED.model, "
    f" updated_at = now()"
)


def _extract_counterparty(reading: dict[str, Any]) -> tuple[dict[str, Any], Any, Any]:
    """Copia `reading` sin `counterparty_tax_id`/`counterparty_name`, devolviendo también los dos
    valores extraídos (para cifrarlos aparte). Nunca muta el dict del llamador."""
    stripped = dict(reading)
    tax_id = stripped.pop("counterparty_tax_id", None)
    name = stripped.pop("counterparty_name", None)
    return stripped, tax_id, name


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
    encryption_key: str,
) -> None:
    """Inserta o reemplaza la comparativa del fichero en el tenant del contexto (idempotente)."""
    original_stripped, original_tax_id, original_name = _extract_counterparty(original_reading)
    enhanced_stripped, enhanced_tax_id, enhanced_name = _extract_counterparty(enhanced_reading)
    await session.execute(
        _UPSERT,
        {
            "company_id": str(company_id),
            "uploaded_file_id": str(uploaded_file_id),
            "original_reading": json.dumps(original_stripped),
            "enhanced_reading": json.dumps(enhanced_stripped),
            "original_counterparty_tax_id": original_tax_id,
            "original_counterparty_name": original_name,
            "enhanced_counterparty_tax_id": enhanced_tax_id,
            "enhanced_counterparty_name": enhanced_name,
            "original_score": original_score,
            "enhanced_score": enhanced_score,
            "winner": winner,
            "engine": engine,
            "model": model,
            "key": encryption_key,
        },
    )

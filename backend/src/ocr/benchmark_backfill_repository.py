"""Descubrimiento de candidatos del lote retroactivo del benchmark real (S6.7 Área C, spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C10/C14).

Llama a `ocr_benchmark_candidates(:limit)` (migración 0030, `SECURITY DEFINER`), que lee A TRAVÉS
de todos los tenants qué facturas ya confirmadas (`invoices`, `is_test = false`) todavía no tienen
las 18 combinaciones completas -- mismo patrón que `ocr.ranking_backfill_repository` (S4.8). Solo
lectura: no escribe nada ni invoca a ningún motor. Llamar desde `shared.db.platform_session` (sin
contexto de tenant), nunca desde `tenant_session`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

__all__ = ["BenchmarkCandidate", "list_benchmark_candidates"]


@dataclass(frozen=True)
class BenchmarkCandidate:
    tenant_id: UUID
    company_id: UUID
    uploaded_file_id: UUID


async def list_benchmark_candidates(session: AsyncSession, limit: int) -> list[BenchmarkCandidate]:
    """Facturas confirmadas con menos de 18 combinaciones ya guardadas, la más reciente primero
    (`confirmed_at DESC`), como mucho `limit` filas."""
    rows = (
        await session.execute(
            text(
                "SELECT tenant_id, company_id, uploaded_file_id "
                "FROM ocr_benchmark_candidates(:limit)"
            ),
            {"limit": limit},
        )
    ).all()
    return [
        BenchmarkCandidate(
            tenant_id=row.tenant_id,
            company_id=row.company_id,
            uploaded_file_id=row.uploaded_file_id,
        )
        for row in rows
    ]

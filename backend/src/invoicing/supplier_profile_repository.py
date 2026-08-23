"""Persistencia transaccional de perfiles de proveedor (R-038)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from invoicing.supplier_profiles import SupplierProfileFeatures

_SELECT = text(
    "SELECT confirmations, invoice_number_patterns, tax_rate_histogram, "
    "tax_line_count_histogram, field_correction_stats "
    "FROM supplier_profiles "
    "WHERE tenant_id = :tenant_id AND company_id = :company_id "
    "AND counterparty_cif_blind_index = :blind_index FOR UPDATE"
)
_INSERT = text(
    "INSERT INTO supplier_profiles (tenant_id, company_id, counterparty_cif_blind_index, "
    "confirmations, invoice_number_patterns, tax_rate_histogram, tax_line_count_histogram, "
    "field_correction_stats, last_seen_at) VALUES (:tenant_id, :company_id, :blind_index, "
    ":confirmations, CAST(:invoice_patterns AS jsonb), CAST(:tax_rates AS jsonb), "
    "CAST(:line_counts AS jsonb), CAST(:corrections AS jsonb), :last_seen_at)"
)
_UPDATE = text(
    "UPDATE supplier_profiles SET confirmations = :confirmations, "
    "invoice_number_patterns = CAST(:invoice_patterns AS jsonb), "
    "tax_rate_histogram = CAST(:tax_rates AS jsonb), "
    "tax_line_count_histogram = CAST(:line_counts AS jsonb), "
    "field_correction_stats = CAST(:corrections AS jsonb), last_seen_at = :last_seen_at, "
    "updated_at = now() WHERE tenant_id = :tenant_id AND company_id = :company_id "
    "AND counterparty_cif_blind_index = :blind_index"
)
_GET = text(
    "SELECT confirmations, invoice_number_patterns, tax_rate_histogram "
    "FROM supplier_profiles WHERE tenant_id = :tenant_id AND company_id = :company_id "
    "AND counterparty_cif_blind_index = :blind_index"
)


async def get(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    company_id: UUID,
    counterparty_cif_blind_index: str,
) -> dict[str, Any] | None:
    row = (
        (
            await session.execute(
                _GET,
                {
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "blind_index": counterparty_cif_blind_index,
                },
            )
        )
        .mappings()
        .first()
    )
    return dict(row) if row is not None else None


async def upsert(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    company_id: UUID,
    counterparty_cif_blind_index: str,
    features: SupplierProfileFeatures,
) -> None:
    """Incrementa contadores bajo lock, dentro de la transacción de confirmación."""
    now = datetime.now(UTC)
    row = (
        (
            await session.execute(
                _SELECT,
                {
                    "tenant_id": tenant_id,
                    "company_id": company_id,
                    "blind_index": counterparty_cif_blind_index,
                },
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        await session.execute(
            _INSERT,
            _params(
                tenant_id,
                company_id,
                counterparty_cif_blind_index,
                confirmations=1,
                invoice_patterns=[features.invoice_number_pattern],
                tax_rates=features.tax_rate_histogram,
                line_counts=features.tax_line_count_histogram,
                corrections=features.field_correction_stats,
                last_seen_at=now,
            ),
        )
        return

    await session.execute(
        _UPDATE,
        _params(
            tenant_id,
            company_id,
            counterparty_cif_blind_index,
            confirmations=int(row["confirmations"]) + 1,
            invoice_patterns=[
                *(row["invoice_number_patterns"] or []),
                features.invoice_number_pattern,
            ],
            tax_rates=_increment_histogram(row["tax_rate_histogram"], features.tax_rate_histogram),
            line_counts=_increment_histogram(
                row["tax_line_count_histogram"], features.tax_line_count_histogram
            ),
            corrections=_increment_histogram(
                row["field_correction_stats"], features.field_correction_stats
            ),
            last_seen_at=now,
        ),
    )


def _params(
    tenant_id: UUID,
    company_id: UUID,
    blind_index: str,
    *,
    confirmations: int,
    invoice_patterns: list[dict[str, str | None]],
    tax_rates: dict[str, int],
    line_counts: dict[str, int],
    corrections: dict[str, int],
    last_seen_at: datetime,
) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "company_id": company_id,
        "blind_index": blind_index,
        "confirmations": confirmations,
        "invoice_patterns": json.dumps(invoice_patterns),
        "tax_rates": json.dumps(tax_rates),
        "line_counts": json.dumps(line_counts),
        "corrections": json.dumps(corrections),
        "last_seen_at": last_seen_at,
    }


def _increment_histogram(
    current: dict[str, int] | None, increment: dict[str, int]
) -> dict[str, int]:
    result = {str(key): int(value) for key, value in (current or {}).items()}
    for key, value in increment.items():
        result[str(key)] = result.get(str(key), 0) + int(value)
    return dict(sorted(result.items()))

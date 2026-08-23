"""Features seguras y reglas de aprendizaje por proveedor (R-038)."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from shared.encryption import blind_index
from shared.tax_id import normalize_tax_id

__all__ = [
    "SupplierProfileEvidence",
    "SupplierProfileFeatures",
    "build_profile_features",
    "profile_evidence",
    "profile_can_influence_decision",
    "supplier_profile_blind_index",
]


@dataclass(frozen=True)
class SupplierProfileFeatures:
    """Incremento mínimo de un perfil, sin copiar la factura confirmada."""

    invoice_number_pattern: dict[str, str | None]
    tax_rate_histogram: dict[str, int]
    tax_line_count_histogram: dict[str, int]
    field_correction_stats: dict[str, int]


@dataclass(frozen=True)
class SupplierProfileEvidence:
    supplier_known: bool
    pattern_match: bool | None
    tax_rate_conflict: bool


def build_profile_features(
    *,
    invoice_number: str | None,
    tax_rates: list[Decimal],
    tax_line_count: int,
    corrections: list[Any],
) -> SupplierProfileFeatures:
    """Construye solo patrones agregados, nunca valores históricos completos."""
    correction_counts = Counter(str(correction.field) for correction in corrections)
    rate_counts = Counter(format(rate.normalize(), "f") for rate in tax_rates if rate.is_finite())
    return SupplierProfileFeatures(
        invoice_number_pattern=_invoice_number_pattern(invoice_number),
        tax_rate_histogram=dict(sorted(rate_counts.items())),
        tax_line_count_histogram={str(tax_line_count): 1},
        field_correction_stats=dict(sorted(correction_counts.items())),
    )


def supplier_profile_blind_index(
    settings: Any, tenant_id: UUID, company_id: UUID, counterparty_cif: str
) -> str:
    """Índice HMAC scoped por tenant y empresa; el CIF nunca se guarda en claro."""
    scope = f"{tenant_id}:{company_id}"
    return blind_index(settings.db_encryption_master_key, scope, normalize_tax_id(counterparty_cif))


def profile_can_influence_decision(confirmations: int) -> bool:
    """Cold start: el perfil solo aporta evidencia después de tres confirmaciones."""
    return confirmations >= 3


def profile_evidence(
    profile: dict[str, Any], *, invoice_number: str | None, tax_rates: list[Decimal]
) -> SupplierProfileEvidence:
    """Compara features maduras como evidencia débil, nunca como sustitución del OCR."""
    if not profile_can_influence_decision(int(profile.get("confirmations", 0))):
        return SupplierProfileEvidence(False, None, False)
    pattern = _invoice_number_pattern(invoice_number)
    known_patterns = profile.get("invoice_number_patterns") or []
    pattern_match = pattern in known_patterns if known_patterns else None
    known_rates = set((profile.get("tax_rate_histogram") or {}).keys())
    tax_rate_conflict = bool(known_rates) and any(
        format(rate.normalize(), "f") not in known_rates for rate in tax_rates if rate.is_finite()
    )
    return SupplierProfileEvidence(True, pattern_match, tax_rate_conflict)


def _invoice_number_pattern(value: str | None) -> dict[str, str | None]:
    if value is None or not value.strip():
        return {"prefix": None, "separator": None, "suffix": "missing"}
    match = re.match(r"^([A-Za-z]+)([-/]).*?(\d+)$", value.strip())
    if match is None:
        return {"prefix": "mixed", "separator": None, "suffix": "mixed"}
    return {"prefix": match.group(1).upper(), "separator": match.group(2), "suffix": "digits"}

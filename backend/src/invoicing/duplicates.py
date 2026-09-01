"""Detección determinista de facturas repetidas (R-052)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ocr.normalization import normalize_invoice_number
from shared.tax_id import normalize_tax_id


@dataclass(frozen=True)
class DuplicateMatch:
    """Coincidencia visible para el usuario, sin incluir datos fiscales de la factura existente."""

    uploaded_file_id: str
    invoice_id: str | None
    kind: str
    matching_fields: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "uploaded_file_id": self.uploaded_file_id,
            "invoice_id": self.invoice_id,
            "kind": self.kind,
            "matching_fields": list(self.matching_fields),
        }


@dataclass(frozen=True)
class DuplicateValues:
    invoice_number: str | None
    own_tax_id: str | None
    counterparty_tax_id: str | None
    total_amount: Decimal | None


def duplicate_match(
    current: DuplicateValues,
    candidate: DuplicateValues,
    *,
    uploaded_file_id: str,
    invoice_id: str | None,
) -> DuplicateMatch | None:
    """Devuelve coincidencia fuerte o sospecha; valores ausentes nunca coinciden."""
    current_number = normalize_invoice_number(current.invoice_number)
    candidate_number = normalize_invoice_number(candidate.invoice_number)
    current_own = normalize_tax_id(current.own_tax_id)
    candidate_own = normalize_tax_id(candidate.own_tax_id)
    current_counterparty = normalize_tax_id(current.counterparty_tax_id)
    candidate_counterparty = normalize_tax_id(candidate.counterparty_tax_id)

    if not current_number or current_number != candidate_number:
        return None
    if not current_own or current_own != candidate_own:
        return None
    if not current_counterparty or current_counterparty != candidate_counterparty:
        return None

    matching_fields = ("invoice_number", "own_tax_id", "counterparty_tax_id")
    if (
        current.total_amount is not None
        and candidate.total_amount is not None
        and current.total_amount == candidate.total_amount
    ):
        return DuplicateMatch(
            uploaded_file_id=uploaded_file_id,
            invoice_id=invoice_id,
            kind="confirmed",
            matching_fields=(*matching_fields, "total_amount"),
        )
    return DuplicateMatch(
        uploaded_file_id=uploaded_file_id,
        invoice_id=invoice_id,
        kind="suspected",
        matching_fields=matching_fields,
    )

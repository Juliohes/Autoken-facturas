"""Reglas puras para decidir el fallback OCR condicional (R-034)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ocr.analysis import STATUS_HARD_FAIL, InvoiceAnalysis
from ocr.extraction import ExtractedInvoice, is_low
from ocr.field_matching import (
    amounts_match,
    dates_match,
    names_match,
    tax_ids_match,
    tax_lines_match,
    texts_match,
)

__all__ = ["fallback_reasons", "has_material_conflict"]


def fallback_reasons(
    invoice: ExtractedInvoice,
    analysis: InvoiceAnalysis,
    *,
    provider_error: str | None = None,
    supplier_profile_conflict: bool = False,
    image_quality_good: bool = False,
) -> tuple[str, ...]:
    """Devuelve los motivos que justifican una segunda lectura, sin ejecutarla.

    El nombre de contraparte con confianza `media` no aparece entre los disparadores: es una
    corrección visual barata y la regla de producción no debe convertirla en una segunda llamada.
    """
    reasons: list[str] = []
    if provider_error:
        reasons.append(provider_error)
    if (
        analysis.counterparty_tax_id is None
        or invoice.issue_date is None
        or invoice.total_amount is None
        or invoice.tax_amount is None
    ):
        reasons.append("critical_field_missing")
    low_confidence = (
        (invoice.issue_date is not None and is_low(invoice.issue_date_confidence))
        or (invoice.total_amount is not None and is_low(invoice.total_confidence))
        or (
            analysis.counterparty_confidence is not None
            and is_low(analysis.counterparty_confidence)
        )
        or (invoice.tax_amount is not None and is_low(invoice.tax_amount_confidence))
    )
    if low_confidence:
        reasons.append("critical_field_low_confidence")
    mod23 = analysis.validations.get("counterparty_mod23")
    if isinstance(mod23, Mapping) and mod23.get("valid") is False:
        reasons.append("counterparty_tax_id_invalid")
    totals = analysis.validations.get("totals")
    if isinstance(totals, Mapping) and totals.get("valid") is False:
        reasons.append("invoice_math_mismatch")
    if supplier_profile_conflict:
        reasons.append("supplier_profile_conflict")
    if analysis.status == STATUS_HARD_FAIL and image_quality_good:
        reasons.append("hard_fail_but_image_quality_good")
    return tuple(dict.fromkeys(reasons))


def has_material_conflict(
    primary: ExtractedInvoice,
    fallback: ExtractedInvoice,
    primary_analysis: InvoiceAnalysis,
    fallback_analysis: InvoiceAnalysis,
) -> bool:
    """Detecta desacuerdos entre valores que ambos motores sí han leído."""
    return any(
        (
            _different(primary.issue_date, fallback.issue_date, dates_match),
            _different(primary.total_amount, fallback.total_amount, amounts_match),
            _different(primary.net_amount, fallback.net_amount, amounts_match),
            _different(primary.tax_amount, fallback.tax_amount, amounts_match),
            _different(
                _tax_line_values(primary),
                _tax_line_values(fallback),
                tax_lines_match,
            ),
            _different(primary.invoice_number, fallback.invoice_number, texts_match),
            _different(
                primary_analysis.counterparty_tax_id,
                fallback_analysis.counterparty_tax_id,
                tax_ids_match,
            ),
            _different(
                primary_analysis.counterparty_name,
                fallback_analysis.counterparty_name,
                names_match,
            ),
        )
    )


def _different(left: Any, right: Any, matcher: Callable[..., bool]) -> bool:
    return left is not None and right is not None and not matcher(left, right)


def _tax_line_values(invoice: ExtractedInvoice) -> tuple[tuple[Any, Any, Any], ...]:
    return tuple((line.rate, line.base, line.cuota) for line in invoice.tax_lines)

"""Comparativa original-vs-realzada de una lectura OCR (S2.10).

Módulo PURO (sin I/O): reutiliza `ocr.analysis.analyze_invoice`, la MISMA regla de negocio que ya
decide `auto_ok`/`needs_review` en producción (S2.3), para puntuar cada lectura con señales
deterministas — nunca con una opinión subjetiva de una IA sobre "cuál es mejor". Ganar es tener más
señales objetivas a favor; un empate exacto da `tie`, nunca un ganador inventado (anti-alucinación
del veredicto, spec C10).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from ocr.analysis import (
    STATUS_AUTO_OK,
    VALIDATION_FIELD_VALID,
    VALIDATION_KEY_COUNTERPARTY_MOD23,
    VALIDATION_KEY_TOTALS,
    InvoiceAnalysis,
    analyze_invoice,
)
from ocr.extraction import ExtractedInvoice, serialize_tax_lines

__all__ = ["Winner", "ComparisonVerdict", "compare_readings", "serialize_reading"]

Winner = Literal["original", "enhanced", "tie"]


@dataclass(frozen=True)
class ComparisonVerdict:
    """Veredicto de comparar la lectura de una imagen original contra su versión realzada."""

    original_analysis: InvoiceAnalysis
    enhanced_analysis: InvoiceAnalysis
    original_score: int
    enhanced_score: int
    winner: Winner


def _score(analysis: InvoiceAnalysis) -> int:
    """Cuenta de señales deterministas a favor de una lectura: mismas señales que ya usa S2.3
    para decidir `auto_ok`/`needs_review`, aquí solo se cuentan en vez de un único booleano."""
    score = 0
    if analysis.status == STATUS_AUTO_OK:
        score += 1
    if analysis.own_tax_id_present:
        score += 1
    mod23 = analysis.validations.get(VALIDATION_KEY_COUNTERPARTY_MOD23)
    if mod23 is not None and mod23.get(VALIDATION_FIELD_VALID):
        score += 1
    totals = analysis.validations.get(VALIDATION_KEY_TOTALS)
    if totals is not None and totals.get(VALIDATION_FIELD_VALID):
        score += 1
    if analysis.counterparty_confidence == "alta":
        score += 1
    return score


def compare_readings(
    original: ExtractedInvoice, enhanced: ExtractedInvoice, own_cif: str
) -> ComparisonVerdict:
    """Puntúa ambas lecturas con el análisis de dominio ya auditado de S2.3 y decide el ganador."""
    original_analysis = analyze_invoice(original, own_cif)
    enhanced_analysis = analyze_invoice(enhanced, own_cif)
    original_score = _score(original_analysis)
    enhanced_score = _score(enhanced_analysis)

    winner: Winner
    if enhanced_score > original_score:
        winner = "enhanced"
    elif original_score > enhanced_score:
        winner = "original"
    else:
        winner = "tie"

    return ComparisonVerdict(
        original_analysis=original_analysis,
        enhanced_analysis=enhanced_analysis,
        original_score=original_score,
        enhanced_score=enhanced_score,
        winner=winner,
    )


def serialize_reading(invoice: ExtractedInvoice, analysis: InvoiceAnalysis) -> dict[str, Any]:
    """Foto JSON-friendly de una lectura + su análisis, para guardar en `ocr_comparison_runs`."""
    return {
        "issue_date": invoice.issue_date.isoformat() if invoice.issue_date is not None else None,
        "total_amount": str(invoice.total_amount) if invoice.total_amount is not None else None,
        "net_amount": str(invoice.net_amount) if invoice.net_amount is not None else None,
        "tax_amount": str(invoice.tax_amount) if invoice.tax_amount is not None else None,
        "tax_lines": serialize_tax_lines(invoice),
        "counterparty_tax_id": analysis.counterparty_tax_id,
        "counterparty_name": analysis.counterparty_name,
        "own_tax_id_present": analysis.own_tax_id_present,
        "confidences": analysis.confidences,
        "validations": analysis.validations,
        "status": analysis.status,
    }

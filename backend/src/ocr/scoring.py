"""Puntuación y serialización de una lectura OCR ya analizada (extraídas de `ocr.comparison`, S4.8).

Módulo PURO: cuenta/serializa señales objetivas del MISMO análisis de dominio que ya usa producción
(S2.3, `ocr.analysis.analyze_invoice`) — nunca una opinión subjetiva de una IA sobre "cuál lectura
es mejor". Compartido entre `ocr.comparison` (S2.10, original-vs-realzada) y `jobs.ocr_ranking`
(S4.8, ranking multi-modelo): la señal de qué hace "buena" una lectura, y su foto JSON-friendly,
viven en un solo sitio (auditoría: `serialize_reading` vivía en `ocr.comparison`, un módulo
específico de S2.10, pese a que S4.8 también la necesita — cohesión, no una dependencia real entre
ambos).
"""

from __future__ import annotations

from typing import Any

from ocr.analysis import (
    STATUS_AUTO_OK,
    VALIDATION_FIELD_VALID,
    VALIDATION_KEY_COUNTERPARTY_MOD23,
    VALIDATION_KEY_TOTALS,
    InvoiceAnalysis,
)
from ocr.extraction import ExtractedInvoice, serialize_tax_lines

__all__ = ["score_analysis", "serialize_reading"]


def score_analysis(analysis: InvoiceAnalysis) -> int:
    """Cuenta de señales deterministas a favor de una lectura (0-5): mismas señales que ya usa
    S2.3 para decidir `auto_ok`/`needs_review`, aquí solo se cuentan en vez de un único booleano."""
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


def serialize_reading(invoice: ExtractedInvoice, analysis: InvoiceAnalysis) -> dict[str, Any]:
    """Foto JSON-friendly de una lectura + su análisis, para guardar en tablas de experimentos."""
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

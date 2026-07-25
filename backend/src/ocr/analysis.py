"""Análisis de dominio de una factura extraída (S2.3): contraparte, validaciones y enrutado.

Módulo PURO (sin I/O): recibe un `ExtractedInvoice` ya reconciliado y el **CIF propio conocido**
(inyectado desde `companies`, no leído) y produce el veredicto de negocio:

- **Contraparte**: el identificador fiscal leído cuyo valor normalizado NO es el CIF propio (el de
  mayor confianza si hay varios); `None` si no hay ninguno (no leída, regla anti-alucinación).
- **CIF propio presente**: si el CIF propio conocido aparece entre los leídos (anti-foto errónea).
  El nombre/CIF propios NO se puntúan: un nombre propio mal leído no enruta a revisión.
- **Validaciones deterministas** (marcan, no corrigen): mód-23 del CIF de contraparte y cuadre
  aritmético de tramos+total (con tolerancia de redondeo).
- **Estado**: `needs_review` si algún campo de oro es dudoso/no leído, el CIF propio no aparece o
  una validación falla; `auto_ok` solo si todo es alto y válido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ocr.extraction import (
    CONFIDENCE_RANK,
    Confidence,
    ExtractedInvoice,
    ExtractedTaxId,
    is_low,
)
from ocr.verification import TaxLine, check_invoice_totals
from shared.tax_id import normalize_tax_id, validate_tax_id

__all__ = [
    "InvoiceAnalysis",
    "STATUS_AUTO_OK",
    "STATUS_NEEDS_REVIEW",
    "VALIDATION_KEY_COUNTERPARTY_MOD23",
    "VALIDATION_KEY_TOTALS",
    "VALIDATION_FIELD_VALID",
    "analyze_invoice",
]

# Estados globales de la extracción (columna `ocr_extractions.status`).
STATUS_AUTO_OK = "auto_ok"
STATUS_NEEDS_REVIEW = "needs_review"

# Claves de `InvoiceAnalysis.validations` (dict sin tipar por ser JSON-friendly de cara a
# `ocr_extractions.validations`). Se exponen como constantes para que otros consumidores del
# análisis (p. ej. `ocr.comparison`, S2.10) no repitan los literales — si cambiaran aquí sin
# actualizar un consumidor con el literal repetido, fallaría en silencio (auditoría).
VALIDATION_KEY_COUNTERPARTY_MOD23 = "counterparty_mod23"
VALIDATION_KEY_TOTALS = "totals"
VALIDATION_FIELD_VALID = "valid"


@dataclass(frozen=True)
class InvoiceAnalysis:
    """Resultado del análisis de dominio de una factura extraída, listo para persistir."""

    counterparty_tax_id: str | None
    counterparty_name: str | None
    counterparty_confidence: Confidence | None
    own_tax_id_present: bool
    status: str
    confidences: dict[str, Any] = field(default_factory=dict)
    validations: dict[str, Any] = field(default_factory=dict)


def analyze_invoice(invoice: ExtractedInvoice, own_cif: str) -> InvoiceAnalysis:
    """Aplica las reglas de negocio de S2.3 a una lectura reconciliada + el CIF propio conocido."""
    own_normalized = normalize_tax_id(own_cif)
    read_values = {normalize_tax_id(tid.value) for tid in invoice.tax_ids if tid.value is not None}
    own_present = own_normalized != "" and own_normalized in read_values

    counterparty = _pick_counterparty(invoice.tax_ids, own_normalized)

    # Validación L1 (mód-23) del CIF de contraparte: solo si hay contraparte leída. Marca, no toca.
    # `_pick_counterparty` ya garantiza `value` no nulo en la candidata elegida.
    mod23: dict[str, Any] | None = None
    if counterparty is not None:
        check = validate_tax_id(counterparty.value)
        mod23 = {VALIDATION_FIELD_VALID: check.valid, "reason": check.reason}

    # Cuadre aritmético: solo verificable con total y al menos un tramo; su ausencia no es un KO
    # (evita falsos descuadres que molestan al usuario).
    totals: dict[str, Any] | None = None
    if invoice.total_amount is not None and invoice.tax_lines:
        lines = [
            TaxLine(base=line.base, iva_pct=line.rate, cuota=line.cuota)
            for line in invoice.tax_lines
        ]
        check = check_invoice_totals(lines, invoice.total_amount)
        totals = {VALIDATION_FIELD_VALID: check.valid, "reason": check.reason}

    confidences = {
        "issue_date": invoice.issue_date_confidence,
        "total": invoice.total_confidence,
        "counterparty": counterparty.confidence if counterparty is not None else None,
    }
    validations = {
        "own_tax_id_present": own_present,
        VALIDATION_KEY_COUNTERPARTY_MOD23: mod23,
        VALIDATION_KEY_TOTALS: totals,
    }

    needs_review = _needs_review(invoice, counterparty, own_present, mod23, totals)
    status = STATUS_NEEDS_REVIEW if needs_review else STATUS_AUTO_OK

    return InvoiceAnalysis(
        counterparty_tax_id=counterparty.value if counterparty is not None else None,
        counterparty_name=counterparty.name if counterparty is not None else None,
        counterparty_confidence=counterparty.confidence if counterparty is not None else None,
        own_tax_id_present=own_present,
        status=status,
        confidences=confidences,
        validations=validations,
    )


def _pick_counterparty(
    tax_ids: tuple[ExtractedTaxId, ...], own_normalized: str
) -> ExtractedTaxId | None:
    """El identificador leído que NO es el propio; si hay varios, el de mayor confianza.

    El CIF propio se inyecta (conocido), no se puntúa como lectura: se descarta de las candidatas.
    """
    candidates = [
        tid
        for tid in tax_ids
        if tid.value is not None and normalize_tax_id(tid.value) != own_normalized
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda tid: CONFIDENCE_RANK[tid.confidence])


def _needs_review(
    invoice: ExtractedInvoice,
    counterparty: ExtractedTaxId | None,
    own_present: bool,
    mod23: dict[str, Any] | None,
    totals: dict[str, Any] | None,
) -> bool:
    """True si CUALQUIER señal exige revisión reforzada (enrutado por confianza + validaciones)."""
    if counterparty is None:  # contraparte no leída
        return True
    if is_low(counterparty.confidence):  # contraparte dudosa
        return True
    if invoice.issue_date is None or is_low(invoice.issue_date_confidence):
        return True
    if invoice.total_amount is None or is_low(invoice.total_confidence):
        return True
    if not own_present:  # el CIF propio no aparece (anti-foto-equivocada)
        return True
    if mod23 is not None and not mod23["valid"]:  # mód-23 KO
        return True
    return totals is not None and not totals["valid"]  # descuadre aritmético

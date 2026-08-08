"""Árbitro por campo: reconcilia las lecturas de N extractores en un `ExtractedInvoice` único.

Los extractores corren en paralelo (`asyncio.gather`) y cada uno propone su lectura de los campos de
oro con su confianza. El árbitro decide, **campo a campo**, con qué valor quedarse. Hoy **N = 1**
(gemini-3-flash, ADR-0016): con una sola lectura el árbitro es la identidad. El diseño per-campo
permite añadir un segundo motor sin reescribir el job: basta ampliar la estrategia de selección.

Módulo puro (sin I/O): entra una secuencia de `ExtractedInvoice`, sale uno reconciliado.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ocr.extraction import CONFIDENCE_RANK, Confidence, ExtractedInvoice

__all__ = ["reconcile"]


@dataclass(frozen=True)
class _Scalar:
    """Valor de un campo escalar de oro con su confianza, tras la reconciliación."""

    value: object
    confidence: Confidence


def reconcile(candidates: Sequence[ExtractedInvoice]) -> ExtractedInvoice:
    """Reconcilia las lecturas de los extractores en un `ExtractedInvoice` (con N=1, identidad).

    - Campos con confianza propia (`issue_date`, `total_amount`, `net_amount`, `tax_amount`,
      `invoice_number`, spec S6.1): gana la lectura NO nula de mayor confianza; si todas son nulas,
      se conserva la nula de mayor confianza declarada.
    - Resto de campos (tramos, identificadores, metadatos): salen de la lectura primaria (la de
      mayor confianza de total). Con N=1 todo sale del mismo candidato.

    El cruce fino de tramos/identificadores entre motores queda diferido (ADR-0016); hoy N=1.
    """
    if not candidates:
        raise ValueError("El árbitro necesita al menos una lectura para reconciliar")

    issue = _best_scalar(candidates, "issue_date", "issue_date_confidence")
    total = _best_scalar(candidates, "total_amount", "total_confidence")
    net = _best_scalar(candidates, "net_amount", "net_amount_confidence")
    tax = _best_scalar(candidates, "tax_amount", "tax_amount_confidence")
    invoice_number = _best_scalar(candidates, "invoice_number", "invoice_number_confidence")
    primary = _primary(candidates)

    return ExtractedInvoice(
        issue_date=issue.value,  # type: ignore[arg-type]  # el escalar preserva el tipo del campo
        issue_date_confidence=issue.confidence,
        total_amount=total.value,  # type: ignore[arg-type]
        total_confidence=total.confidence,
        net_amount=net.value,  # type: ignore[arg-type]
        net_amount_confidence=net.confidence,
        tax_amount=tax.value,  # type: ignore[arg-type]
        tax_amount_confidence=tax.confidence,
        invoice_number=invoice_number.value,  # type: ignore[arg-type]
        invoice_number_confidence=invoice_number.confidence,
        tax_lines=primary.tax_lines,
        tax_ids=primary.tax_ids,
        engine=primary.engine,
        model=primary.model,
        raw=primary.raw,
    )


def _best_scalar(
    candidates: Sequence[ExtractedInvoice], value_attr: str, conf_attr: str
) -> _Scalar:
    """Mejor lectura de un campo escalar: valor no nulo de mayor confianza (o el mejor nulo)."""

    def key(invoice: ExtractedInvoice) -> tuple[int, int]:
        value = getattr(invoice, value_attr)
        confidence: Confidence = getattr(invoice, conf_attr)
        # Prioriza una lectura con valor sobre una nula; a igualdad, la de mayor confianza.
        return (0 if value is None else 1, CONFIDENCE_RANK[confidence])

    best = max(candidates, key=key)
    return _Scalar(value=getattr(best, value_attr), confidence=getattr(best, conf_attr))


def _primary(candidates: Sequence[ExtractedInvoice]) -> ExtractedInvoice:
    """Lectura primaria: la de mayor confianza en el total (desempata el orden de llegada)."""
    return max(candidates, key=lambda inv: CONFIDENCE_RANK[inv.total_confidence])

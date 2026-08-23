"""Análisis de dominio de una factura extraída (S2.3): contraparte, validaciones y enrutado.

Módulo PURO (sin I/O): recibe un `ExtractedInvoice` ya reconciliado y el **CIF propio conocido**
(inyectado desde `companies`, no leído) y produce el veredicto de negocio:

- **Contraparte**: el identificador fiscal leído cuyo valor normalizado NO es el CIF propio (el de
  mayor confianza si hay varios); `None` si no hay ninguno (no leída, regla anti-alucinación).
- **CIF propio presente**: si el CIF propio conocido aparece entre los leídos (anti-foto errónea).
  El nombre/CIF propios NO se puntúan: un nombre propio mal leído no enruta a revisión.
- **Validaciones deterministas** (marcan Y degradan la confianza mostrada, no solo el enrutado,
  S6.14 C6): mód-23 del CIF de contraparte y cuadre aritmético de tramos+total (con tolerancia de
  redondeo). El `ExtractedInvoice` original (lo que dijo el motor) NO se toca, solo el diccionario
  `confidences` que se persiste y se muestra — trazabilidad para auditoría/laboratorio (S6.2).
- **Estado**: `hard_fail` (S6.14, captura ilegible: repetir la foto, no revisar campos vacíos) si la
  imagen en sí parece el problema; si no, `needs_review` si algún campo de oro es dudoso/no leído,
  el CIF propio no aparece o una validación falla; `auto_ok` solo si todo es alto y válido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ocr.confidence import Evidence, compute_field_confidence
from ocr.extraction import (
    CONFIDENCE_RANK,
    Confidence,
    ExtractedInvoice,
    ExtractedTaxId,
    is_low,
)
from ocr.verification import TaxLine, check_invoice_totals, check_invoice_totals_detailed
from shared.tax_id import normalize_tax_id, validate_tax_id

__all__ = [
    "InvoiceAnalysis",
    "STATUS_AUTO_OK",
    "STATUS_NEEDS_REVIEW",
    "STATUS_HARD_FAIL",
    "VALIDATION_KEY_COUNTERPARTY_MOD23",
    "VALIDATION_KEY_TOTALS",
    "VALIDATION_FIELD_VALID",
    "analyze_invoice",
]

# Estados globales de la extracción (columna `ocr_extractions.status`).
STATUS_AUTO_OK = "auto_ok"
STATUS_NEEDS_REVIEW = "needs_review"
# S6.14 C7: "captura ilegible" — la imagen en sí es el problema, no un campo dudoso concreto. El
# fichero transiciona a `invoice_intake.constants.FileStatus.CAPTURE_UNREADABLE` (jobs.ocr.run_ocr),
# un estado propio distinguible de `needs_review` (aquí no tiene sentido abrir un formulario con
# campos vacíos) y de `ocr_failed` (aquí el motor SÍ respondió, solo que con nada aprovechable).
STATUS_HARD_FAIL = "hard_fail"

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
    system_confidences: dict[str, Any] = field(default_factory=dict)
    validations: dict[str, Any] = field(default_factory=dict)


def analyze_invoice(invoice: ExtractedInvoice, own_cif: str) -> InvoiceAnalysis:
    """Aplica las reglas de negocio de S2.3 (+ S6.14) a una lectura reconciliada + el CIF propio."""
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
        check = check_invoice_totals(
            lines, invoice.total_amount, irpf_cuota=invoice.irpf_amount or Decimal(0)
        )
        detail = check_invoice_totals_detailed(
            lines, invoice.total_amount, irpf_cuota=invoice.irpf_amount or Decimal(0)
        )
        totals = {
            VALIDATION_FIELD_VALID: check.valid,
            "reason": check.reason,
            "detail": detail.model_dump(mode="json"),
        }

    # Mismas claves que `fields` en la respuesta de `review` (`invoicing.service.review`):
    # el frontend indexa `review.confidences[<nombre del campo>]` con esos nombres exactos
    # (`total_amount`, `counterparty_tax_id`), no con una forma corta (bug real encontrado
    # 2026-08-07: con "total"/"counterparty" el frontend nunca encontraba la confianza real y
    # esos dos campos salían siempre como "no leído" aunque el motor hubiera leído alta confianza).
    confidences: dict[str, Any] = {
        "issue_date": invoice.issue_date_confidence,
        "total_amount": invoice.total_confidence,
        "counterparty_tax_id": counterparty.value_confidence if counterparty is not None else None,
        # S6.14: confianza propia del nombre de contraparte (antes ausente de `confidences`).
        "counterparty_name": counterparty.name_confidence if counterparty is not None else None,
        # S6.1: número de factura, base imponible e IVA total pasan a ser campos de oro con
        # confianza propia (antes `net_amount`/`tax_amount` quedaban huérfanos de confianza).
        "invoice_number": invoice.invoice_number_confidence,
        "net_amount": invoice.net_amount_confidence,
        "tax_amount": invoice.tax_amount_confidence,
        "irpf_rate": invoice.irpf_rate_confidence if invoice.irpf_rate is not None else None,
        "irpf_amount": invoice.irpf_amount_confidence if invoice.irpf_amount is not None else None,
    }

    # S6.14 C6: una validación determinista fallida degrada la confianza PERSISTIDA/MOSTRADA, no
    # solo el enrutado — antes, un CIF con mód-23 KO o un descuadre podían seguir mostrándose como
    # "alta" (la etiqueta original del motor) aunque ya se supiera, con certeza, que algo fallaba.
    # El `ExtractedInvoice` original (`invoice`, lo que dijo el motor) NO se toca: solo este dict.
    if mod23 is not None and not mod23[VALIDATION_FIELD_VALID]:
        confidences["counterparty_tax_id"] = "baja"
    if totals is not None and not totals[VALIDATION_FIELD_VALID]:
        confidences["total_amount"] = "baja"

    system_confidences = _compute_system_confidences(
        invoice, counterparty, mod23=mod23, totals=totals
    )
    confidences["_system_confidence"] = system_confidences

    unknown_tax_rates = invoice.raw.get("_unknown_tax_rates", [])
    if not isinstance(unknown_tax_rates, list):
        unknown_tax_rates = []
    validations = {
        "own_tax_id_present": own_present,
        VALIDATION_KEY_COUNTERPARTY_MOD23: mod23,
        VALIDATION_KEY_TOTALS: totals,
        "tax_rate_policy": {
            VALIDATION_FIELD_VALID: not unknown_tax_rates,
            "unknown_tax_rate": bool(unknown_tax_rates),
            "rates": unknown_tax_rates,
        },
    }

    # S6.14 C7: captura ilegible (la imagen en sí es el problema) se decide ANTES que needs_review,
    # sobre las confianzas AUTOREPORTADAS por el motor (no las ya degradadas arriba): si se cumple,
    # no hace falta seguir comprobando needs_review.
    if _is_capture_unreadable(invoice, counterparty):
        status = STATUS_HARD_FAIL
    else:
        needs_review = _needs_review(
            invoice, counterparty, own_present, mod23, totals, bool(unknown_tax_rates)
        )
        status = STATUS_NEEDS_REVIEW if needs_review else STATUS_AUTO_OK

    return InvoiceAnalysis(
        counterparty_tax_id=counterparty.value if counterparty is not None else None,
        counterparty_name=counterparty.name if counterparty is not None else None,
        counterparty_confidence=counterparty.value_confidence if counterparty is not None else None,
        own_tax_id_present=own_present,
        status=status,
        confidences=confidences,
        system_confidences=system_confidences,
        validations=validations,
    )


def _pick_counterparty(
    tax_ids: tuple[ExtractedTaxId, ...], own_normalized: str
) -> ExtractedTaxId | None:
    """El identificador leído que NO es el propio; si hay varios, el de mayor `value_confidence`.

    El CIF propio se inyecta (conocido), no se puntúa como lectura: se descarta de las candidatas.
    Rankea por `value_confidence` (S6.14), no por una confianza combinada: lo que decide CUÁL
    identificador es la contraparte es cuánto se fía el motor del CIF, no de su nombre asociado.
    """
    candidates = [
        tid
        for tid in tax_ids
        if tid.value is not None and normalize_tax_id(tid.value) != own_normalized
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda tid: CONFIDENCE_RANK[tid.value_confidence])


def _needs_review(
    invoice: ExtractedInvoice,
    counterparty: ExtractedTaxId | None,
    own_present: bool,
    mod23: dict[str, Any] | None,
    totals: dict[str, Any] | None,
    unknown_tax_rate: bool,
) -> bool:
    """True si CUALQUIER señal exige revisión reforzada (enrutado por confianza + validaciones)."""
    if counterparty is None:  # contraparte no leída
        return True
    if is_low(counterparty.value_confidence):  # CIF de contraparte dudoso: SIN relajar (S6.14 C4)
        return True
    # S6.14 C4/C5: el nombre es una corrección barata (visual, sin validación externa) frente al
    # CIF (impacto fiscal real). Dato empírico del bench S6.7 (29 facturas de Setex): el CIF acierta
    # el 89,66% de las veces y el nombre solo el 58,62% — exigir también "alta" en el nombre
    # generaría revisión casi constante sin beneficio real (el humano lo corrige gratis al mirar la
    # factura). Solo bloquea un nombre "baja" o no legible; "media" pasa sin frenar.
    if counterparty.name is None or counterparty.name_confidence == "baja":
        return True
    if invoice.issue_date is None or is_low(invoice.issue_date_confidence):
        return True
    if invoice.total_amount is None or is_low(invoice.total_confidence):
        return True
    # S6.1: número de factura, base imponible e IVA total, mismo criterio que fecha/total.
    if invoice.invoice_number is None or is_low(invoice.invoice_number_confidence):
        return True
    if invoice.net_amount is None or is_low(invoice.net_amount_confidence):
        return True
    if invoice.tax_amount is None or is_low(invoice.tax_amount_confidence):
        return True
    if invoice.irpf_rate is not None and is_low(invoice.irpf_rate_confidence):
        return True
    if invoice.irpf_amount is not None and is_low(invoice.irpf_amount_confidence):
        return True
    if not own_present:  # el CIF propio no aparece (anti-foto-equivocada)
        return True
    if mod23 is not None and not mod23["valid"]:  # mód-23 KO
        return True
    if unknown_tax_rate:
        return True
    return totals is not None and not totals["valid"]  # descuadre aritmético


def _compute_system_confidences(
    invoice: ExtractedInvoice,
    counterparty: ExtractedTaxId | None,
    *,
    mod23: dict[str, Any] | None,
    totals: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Combina la confianza declarada con validaciones y consenso ya trazado."""
    trace = invoice.raw.get("_consensus", {})
    if not isinstance(trace, dict):
        trace = {}
    fields: dict[str, tuple[Any, Confidence | None]] = {
        "issue_date": (invoice.issue_date, invoice.issue_date_confidence),
        "total_amount": (invoice.total_amount, invoice.total_confidence),
        "invoice_number": (invoice.invoice_number, invoice.invoice_number_confidence),
        "net_amount": (invoice.net_amount, invoice.net_amount_confidence),
        "tax_amount": (invoice.tax_amount, invoice.tax_amount_confidence),
        "irpf_rate": (invoice.irpf_rate, invoice.irpf_rate_confidence),
        "irpf_amount": (invoice.irpf_amount, invoice.irpf_amount_confidence),
        "counterparty_tax_id": (
            counterparty.value if counterparty is not None else None,
            counterparty.value_confidence if counterparty is not None else None,
        ),
        "counterparty_name": (
            counterparty.name if counterparty is not None else None,
            counterparty.name_confidence if counterparty is not None else None,
        ),
    }
    result: dict[str, dict[str, Any]] = {}
    for field_name, (value, provider_confidence) in fields.items():
        field_trace = trace.get(field_name, {})
        if not isinstance(field_trace, dict):
            field_trace = {}
        reasons = field_trace.get("reasons", [])
        sources = field_trace.get("sources", [])
        if not isinstance(reasons, list):
            reasons = []
        if not isinstance(sources, list):
            sources = []
        invalid_reason: str | None = None
        valid_reason: str | None = None
        if field_name == "counterparty_tax_id" and mod23 is not None:
            valid_reason = "tax_id_checksum_ok"
            invalid_reason = "tax_id_checksum_failed"
        elif field_name == "total_amount" and totals is not None:
            valid_reason = "invoice_math_ok"
            invalid_reason = "invoice_math_failed"
        validation = mod23 if field_name == "counterparty_tax_id" else totals
        validation_is_valid = (
            validation is not None and validation.get(VALIDATION_FIELD_VALID) is True
        )
        validation_is_invalid = (
            validation is not None and validation.get(VALIDATION_FIELD_VALID) is False
        )
        evidence = Evidence(
            provider_confidence=_confidence_score(provider_confidence),
            primary_high=provider_confidence == "alta",
            fallback_agrees="engines_agree" in reasons,
            deterministic_valid=valid_reason is not None and validation_is_valid,
            deterministic_invalid=invalid_reason is not None and validation_is_invalid,
            deterministic_valid_reason=valid_reason or "deterministic_valid",
            deterministic_invalid_reason=invalid_reason or "deterministic_invalid",
            fallback_used=len(sources) > 1,
            engine_conflict=field_trace.get("status") == "conflict"
            or "engines_disagree" in reasons,
            field_present=value is not None,
        )
        confidence = compute_field_confidence(evidence)
        result[field_name] = {
            "provider_confidence": evidence.provider_confidence,
            "system_confidence": confidence.score,
            "reasons": list(dict.fromkeys([*reasons, *confidence.reasons])),
        }
    return result


def _confidence_score(confidence: Confidence | None) -> float | None:
    if confidence is None:
        return None
    return {"alta": 1.0, "media": 0.6, "baja": 0.2}[confidence]


def _is_capture_unreadable(invoice: ExtractedInvoice, counterparty: ExtractedTaxId | None) -> bool:
    """True si la captura parece ilegible (S6.14 C7): la imagen es el problema, no un campo dudoso.

    Se evalúa sobre las confianzas AUTOREPORTADAS por el motor (antes de cualquier degradación
    determinista de `analyze_invoice`, que refleja validaciones de negocio, no legibilidad de la
    imagen) y ANTES de decidir `needs_review`/`auto_ok`. Dos criterios, cualquiera basta:

    (a) los 3 campos más fundamentales -contraparte, total, fecha- no se leyeron NINGUNO a la vez
        (spec §5: sigue contando aunque otro campo suelto tenga confianza alta).
    (b) de los campos de oro con valor SÍ leído (fecha, total, base, IVA, número de factura, y el
        CIF/nombre de contraparte si hay), el 100% declara confianza "baja". Si no hay NINGÚN campo
        con valor, este criterio no se dispara por sí solo (ya lo cubre, en ese caso, el (a)).
    """
    if counterparty is None and invoice.total_amount is None and invoice.issue_date is None:
        return True

    confidences_with_value: list[Confidence] = []
    if invoice.issue_date is not None:
        confidences_with_value.append(invoice.issue_date_confidence)
    if invoice.total_amount is not None:
        confidences_with_value.append(invoice.total_confidence)
    if invoice.net_amount is not None:
        confidences_with_value.append(invoice.net_amount_confidence)
    if invoice.tax_amount is not None:
        confidences_with_value.append(invoice.tax_amount_confidence)
    if invoice.irpf_rate is not None:
        confidences_with_value.append(invoice.irpf_rate_confidence)
    if invoice.irpf_amount is not None:
        confidences_with_value.append(invoice.irpf_amount_confidence)
    if invoice.invoice_number is not None:
        confidences_with_value.append(invoice.invoice_number_confidence)
    if counterparty is not None:
        confidences_with_value.append(counterparty.value_confidence)
        if counterparty.name is not None:
            confidences_with_value.append(counterparty.name_confidence)

    if not confidences_with_value:
        return False
    return all(confidence == "baja" for confidence in confidences_with_value)

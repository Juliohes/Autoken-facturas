"""Árbitro por campo para reconciliar lecturas OCR (R-035)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ocr.extraction import (
    CONFIDENCE_RANK,
    Confidence,
    ExtractedInvoice,
    ExtractedTaxId,
)
from ocr.normalization import (
    normalize_amount,
    normalize_date,
    normalize_invoice_number,
    normalize_name,
    normalize_tax_id,
)

__all__ = [
    "FieldCandidate",
    "FieldDecision",
    "decide_field",
    "reconcile",
]

ConsensusStatus = Literal["accepted", "uncertain", "conflict"]


@dataclass(frozen=True)
class FieldCandidate:
    """Una propuesta de un motor para un campo, con valor comparable y trazabilidad."""

    field: str
    normalized_value: str | None
    raw_value: object
    engine: str
    model: str
    provider_confidence: float | None


class FieldDecision(BaseModel):
    """Decisión explicable de consenso para un campo."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    value: object | None
    score: float
    status: ConsensusStatus
    sources: list[str]
    reasons: list[str]


_SCALAR_FIELDS: tuple[tuple[str, str, Callable[[Any], str | None]], ...] = (
    ("issue_date", "issue_date_confidence", normalize_date),
    ("total_amount", "total_confidence", normalize_amount),
    ("net_amount", "net_amount_confidence", normalize_amount),
    ("tax_amount", "tax_amount_confidence", normalize_amount),
    ("irpf_rate", "irpf_rate_confidence", normalize_amount),
    ("irpf_amount", "irpf_amount_confidence", normalize_amount),
    ("invoice_number", "invoice_number_confidence", normalize_invoice_number),
)

_CONFIDENCE_SCORE: dict[Confidence, float] = {"alta": 1.0, "media": 0.6, "baja": 0.2}
_MARGIN_THRESHOLD = 0.2


def decide_field(
    candidates: Sequence[FieldCandidate], *, supplier_normalized_value: str | None = None
) -> FieldDecision:
    """Agrupa evidencia normalizada y devuelve una decisión sin efectos secundarios."""
    if not candidates:
        raise ValueError("El consenso necesita al menos una propuesta")

    groups: dict[str, list[FieldCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.normalized_value is not None:
            groups[candidate.normalized_value].append(candidate)

    if not groups:
        return FieldDecision(
            value=None,
            score=0.0,
            status="uncertain",
            sources=[],
            reasons=["critical_field_missing"],
        )

    def group_score(group: list[FieldCandidate]) -> float:
        evidence = sum(_evidence(candidate) for candidate in group)
        if (
            supplier_normalized_value is not None
            and group[0].normalized_value == supplier_normalized_value
        ):
            evidence += 0.25
        return evidence

    ranked = sorted(groups.values(), key=group_score, reverse=True)
    winner = ranked[0]
    winner_score = group_score(winner)
    runner_score = (
        group_score(ranked[1]) if len(ranked) > 1 else 0.0
    )
    score = min(1.0, winner_score / max(len(candidates), 1))
    sources = [f"{candidate.engine}:{candidate.model}" for candidate in winner]
    reasons = (
        ["primary_high"]
        if any(candidate.provider_confidence == 1.0 for candidate in winner)
        else []
    )
    if supplier_normalized_value == winner[0].normalized_value:
        reasons.append("supplier_known")

    if len(ranked) == 1:
        status: ConsensusStatus = "accepted" if score >= 0.5 else "uncertain"
        reasons.append("engines_agree" if len(winner) > 1 else "single_source")
    elif winner_score - runner_score >= _MARGIN_THRESHOLD:
        status = "accepted"
        reasons.append("margin_over_threshold")
    else:
        status = "conflict"
        reasons.append("engines_disagree")
    if supplier_normalized_value is not None and supplier_normalized_value not in groups:
        reasons.append("supplier_profile_conflict")

    return FieldDecision(
        value=winner[0].raw_value if status == "accepted" else None,
        score=score,
        status=status,
        sources=sources,
        reasons=reasons,
    )


def reconcile(
    candidates: Sequence[ExtractedInvoice], *, consensus_mode: str = "per_field"
) -> ExtractedInvoice:
    """Reconcilia campos escalares; `primary_only` conserva la lectura primaria completa."""
    if not candidates:
        raise ValueError("El árbitro necesita al menos una lectura para reconciliar")
    if consensus_mode == "primary_only":
        return _primary(candidates)
    if consensus_mode != "per_field":
        raise ValueError(f"Modo de consenso no soportado: {consensus_mode}")

    primary = candidates[0]
    decisions: dict[str, FieldDecision] = {}
    values: dict[str, Any] = {}
    confidences: dict[str, Confidence] = {}
    for field, confidence_field, normalizer in _SCALAR_FIELDS:
        field_candidates = [
            FieldCandidate(
                field=field,
                normalized_value=normalizer(getattr(invoice, field)),
                raw_value=getattr(invoice, field),
                engine=invoice.engine,
                model=invoice.model,
                provider_confidence=_CONFIDENCE_SCORE[getattr(invoice, confidence_field)],
            )
            for invoice in candidates
        ]
        decision = decide_field(field_candidates)
        decisions[field] = decision
        values[field] = decision.value
        confidences[field] = _confidence_for_decision(decision, field_candidates)

    for field, normalizer, raw_value in (
        ("tax_ids", _normalize_tax_ids, primary.tax_ids),
        ("tax_lines", _normalize_tax_lines, primary.tax_lines),
    ):
        collection_candidates = [
            FieldCandidate(
                field=field,
                normalized_value=normalizer(invoice),
                raw_value=getattr(invoice, field),
                engine=invoice.engine,
                model=invoice.model,
                provider_confidence=_CONFIDENCE_SCORE[invoice.total_confidence],
            )
            for invoice in candidates
        ]
        decision = decide_field(collection_candidates)
        decisions[field] = decision
        if field == "tax_ids" and decision.status == "accepted":
            values[field] = _merge_tax_ids(candidates)
        else:
            values[field] = decision.value if decision.value is not None else raw_value

    trace = {
        field: {
            "score": decision.score,
            "status": decision.status,
            "sources": decision.sources,
            "reasons": decision.reasons,
        }
        for field, decision in decisions.items()
    }
    raw = dict(primary.raw)
    raw["_consensus"] = trace
    return ExtractedInvoice(
        issue_date=values["issue_date"],
        issue_date_confidence=confidences["issue_date"],
        total_amount=values["total_amount"],
        total_confidence=confidences["total_amount"],
        net_amount=values["net_amount"],
        net_amount_confidence=confidences["net_amount"],
        tax_amount=values["tax_amount"],
        tax_amount_confidence=confidences["tax_amount"],
        irpf_rate=values["irpf_rate"],
        irpf_rate_confidence=confidences["irpf_rate"],
        irpf_amount=values["irpf_amount"],
        irpf_amount_confidence=confidences["irpf_amount"],
        invoice_number=values["invoice_number"],
        invoice_number_confidence=confidences["invoice_number"],
        tax_lines=values["tax_lines"],
        tax_ids=values["tax_ids"],
        engine=primary.engine,
        model=primary.model,
        raw=raw,
    )


def _evidence(candidate: FieldCandidate) -> float:
    return candidate.provider_confidence if candidate.provider_confidence is not None else 0.5


def _confidence_for_decision(
    decision: FieldDecision, candidates: Sequence[FieldCandidate]
) -> Confidence:
    if decision.status == "conflict":
        return "baja"
    available_confidences = [
        candidate.provider_confidence or 0.0
        for candidate in candidates
        if candidate.normalized_value is not None
    ]
    if not available_confidences:
        return "baja"
    confidence = max(available_confidences)
    if confidence >= 0.8:
        return "alta"
    if confidence >= 0.5:
        return "media"
    return "baja"


def _normalize_tax_ids(invoice: ExtractedInvoice) -> str:
    values = sorted(
        normalized
        for tax_id in invoice.tax_ids
        if (normalized := normalize_tax_id(tax_id.value)) is not None
    )
    return "|".join(values)


def _merge_tax_ids(candidates: Sequence[ExtractedInvoice]) -> tuple[ExtractedTaxId, ...]:
    """Une el mismo CIF/NIF leído por varios motores y elige el mejor nombre original."""
    grouped: dict[str, list[ExtractedTaxId]] = defaultdict(list)
    for invoice in candidates:
        for tax_id in invoice.tax_ids:
            normalized = normalize_tax_id(tax_id.value)
            if normalized is not None:
                grouped[normalized].append(tax_id)

    merged: list[ExtractedTaxId] = []
    for tax_ids in grouped.values():
        best_value = max(tax_ids, key=lambda item: CONFIDENCE_RANK[item.value_confidence])
        named = [item for item in tax_ids if normalize_name(item.name) is not None]
        best_name = (
            max(named, key=lambda item: CONFIDENCE_RANK[item.name_confidence])
            if named
            else best_value
        )
        merged.append(
            ExtractedTaxId(
                value=best_value.value,
                name=best_name.name,
                value_confidence=best_value.value_confidence,
                name_confidence=best_name.name_confidence,
            )
        )
    return tuple(merged)


def _normalize_tax_lines(invoice: ExtractedInvoice) -> str:
    values = sorted(
        ":".join(
            (
                normalize_amount(line.rate) or "",
                normalize_amount(line.base) or "",
                normalize_amount(line.cuota) or "",
            )
        )
        for line in invoice.tax_lines
    )
    return "|".join(values)


def _primary(candidates: Sequence[ExtractedInvoice]) -> ExtractedInvoice:
    """Devuelve la primera lectura, que el worker entrega como primario real."""
    return candidates[0]

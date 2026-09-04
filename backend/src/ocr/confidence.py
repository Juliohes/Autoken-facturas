"""Score explicable de confianza sistémica por campo (R-036)."""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["ConfidenceResult", "Evidence", "compute_field_confidence"]


@dataclass(frozen=True)
class Evidence:
    """Señales observables que explican la confianza de un campo."""

    provider_confidence: float | None = None
    primary_high: bool = False
    fallback_agrees: bool = False
    deterministic_valid: bool = False
    deterministic_invalid: bool = False
    deterministic_valid_reason: str = "deterministic_valid"
    deterministic_invalid_reason: str = "deterministic_invalid"
    supplier_known: bool = False
    supplier_pattern_match: bool = False
    supplier_pattern_conflict: bool = False
    image_low_quality: bool = False
    fallback_used: bool = False
    engine_conflict: bool = False
    fallback_only: bool = False
    field_present: bool = True


@dataclass(frozen=True)
class ConfidenceResult:
    """Resultado calibrable y explicable, deliberadamente no científico."""

    score: float
    reasons: list[str] = field(default_factory=list)


def compute_field_confidence(evidence: Evidence) -> ConfidenceResult:
    """Calcula inicialmente con reglas transparentes y devuelve códigos de motivo."""
    if not evidence.field_present:
        missing_reasons = ["critical_field_missing"]
        if evidence.engine_conflict:
            missing_reasons.append("engines_disagree")
        if evidence.fallback_used:
            missing_reasons.append("fallback_used")
        return ConfidenceResult(0.0, missing_reasons)

    score = 0.50
    reasons: list[str] = []
    if evidence.primary_high or (
        evidence.provider_confidence is not None and evidence.provider_confidence >= 0.8
    ):
        score += 0.15
        reasons.append("primary_high")
    if evidence.fallback_agrees:
        score += 0.20
        reasons.append("engines_agree")
    if evidence.deterministic_valid:
        score += 0.15
    if evidence.deterministic_invalid:
        score = min(score, 0.35)
    if evidence.supplier_known:
        score += 0.10
        reasons.append("supplier_known")
    if evidence.supplier_pattern_match:
        score += 0.05
        reasons.append("supplier_pattern_match")
    if evidence.supplier_pattern_conflict:
        score -= 0.15
        reasons.append("supplier_pattern_conflict")
    if evidence.image_low_quality:
        score -= 0.15
        reasons.append("image_low_quality")
    if evidence.fallback_used:
        reasons.append("fallback_used")
    if evidence.engine_conflict:
        score -= 0.20
        reasons.append("engines_disagree")
    if evidence.fallback_only:
        score -= 0.10
        reasons.append("fallback_only")
    if evidence.deterministic_valid:
        reasons.append(evidence.deterministic_valid_reason)
    if evidence.deterministic_invalid:
        reasons.append(evidence.deterministic_invalid_reason)

    return ConfidenceResult(max(0.0, min(1.0, score)), list(dict.fromkeys(reasons)))

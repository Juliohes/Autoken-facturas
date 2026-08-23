"""Métricas puras del contrato de benchmark comparable R-032."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ocr.benchmark_scoring import BenchmarkScore

__all__ = ["BenchmarkMetrics", "calculate_metrics"]


# Son los campos cuya exactitud puede cambiar directamente el tratamiento fiscal de la factura.
_CRITICAL_FIELDS = frozenset(
    {"counterparty_tax_id", "issue_date", "total_amount", "tax_amount"}
)
_SCALAR_FIELDS = (
    "counterparty_tax_id",
    "counterparty_name",
    "invoice_number",
    "issue_date",
    "total_amount",
    "net_amount",
    "tax_amount",
)


@dataclass(frozen=True)
class BenchmarkMetrics:
    """Métricas de una lectura, sin rellenar con ceros los datos no disponibles."""

    field_exact_accuracy: float | None
    critical_field_accuracy: float | None
    all_critical_exact: bool | None
    tax_lines_accuracy: bool | None
    arithmetic_valid_after_extraction: bool | None
    hallucination_flags: tuple[str, ...]
    manual_corrections_per_invoice: int | None


def _has_value(value: object) -> bool:
    return value is not None and value != "" and value != []


def _ratio(matches: list[bool | None]) -> float | None:
    comparable = [match for match in matches if match is not None]
    if not comparable:
        return None
    return sum(comparable) / len(comparable)


def calculate_metrics(
    score: BenchmarkScore,
    reading: Mapping[str, object],
    truth: Mapping[str, object],
    *,
    arithmetic_valid_after_extraction: bool | None,
) -> BenchmarkMetrics:
    """Calcula las métricas R-032 con la misma puntuación que el benchmark.

    Para ejecuciones directas sin la factura confirmada, las correcciones se estiman solo cuando
    todos los campos puntuables tienen ground truth. El job de producción reemplaza esa estimación
    por el conteo real de `ocr_corrections`; si el corpus no contiene esa información, se deja
    `None`.
    """
    scalar_matches = [field_score.match for field_score in score.field_scores]
    critical_matches = [
        field_score.match
        for field_score in score.field_scores
        if field_score.field in _CRITICAL_FIELDS
    ]

    hallucinations = [
        field
        for field in _SCALAR_FIELDS
        if _has_value(reading.get(field)) and not _has_value(truth.get(field))
    ]
    if _has_value(reading.get("tax_lines")) and not _has_value(truth.get("tax_lines")):
        hallucinations.append("tax_lines")

    all_matches = [*scalar_matches, score.tax_lines_matched]
    has_complete_ground_truth = all(match is not None for match in all_matches)
    corrections = (
        sum(match is False for match in all_matches) if has_complete_ground_truth else None
    )

    return BenchmarkMetrics(
        field_exact_accuracy=_ratio(scalar_matches + [score.tax_lines_matched]),
        critical_field_accuracy=_ratio(critical_matches),
        all_critical_exact=(
            all(match is True for match in critical_matches)
            if any(match is not None for match in critical_matches)
            else None
        ),
        tax_lines_accuracy=score.tax_lines_matched,
        arithmetic_valid_after_extraction=arithmetic_valid_after_extraction,
        hallucination_flags=tuple(hallucinations),
        manual_corrections_per_invoice=corrections,
    )

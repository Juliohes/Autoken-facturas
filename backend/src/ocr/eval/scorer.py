"""Scorer de lectura del bench OCR (1.2).

Mide, por factura y de forma tolerante al formato, qué campos del ground truth capturó el motor en
su texto (recall de lectura). Agrega por motor para alimentar el ADR-0007 (motor ganador), con foco
en el recall de los identificadores fiscales (lo que más falla y más importa, §11.8).
"""

from __future__ import annotations

from dataclasses import dataclass

from ocr.eval.models import GroundTruth
from ocr.eval.normalize import amount_variants, date_matches, normalize_tax_id, normalize_text


@dataclass(frozen=True)
class FieldResult:
    """Resultado de un campo: si el motor lo capturó (`found`) y qué se esperaba (`expected`)."""

    field: str  # "tax_id" | "issue_date" | "total_amount" | "net_amount" | "tax_amount"
    expected: str
    found: bool


@dataclass(frozen=True)
class ReadingScore:
    """Puntuación de un motor sobre una factura."""

    invoice_id: str
    engine: str
    results: tuple[FieldResult, ...]

    @property
    def recall(self) -> float:
        """Fracción de campos capturados (0.0 si no había campos que puntuar)."""
        if not self.results:
            return 0.0
        return sum(r.found for r in self.results) / len(self.results)


@dataclass(frozen=True)
class EngineAggregate:
    """Agregado de un motor sobre todas las facturas del dataset."""

    engine: str
    invoices: int
    recall: float  # recall global (todos los campos)
    tax_id_recall: float  # recall solo de los identificadores fiscales


def score_reading(ground_truth: GroundTruth, text: str, *, engine: str) -> ReadingScore:
    """Puntúa el texto de un motor contra el ground truth de una factura."""
    normalized = normalize_text(text)
    results: list[FieldResult] = []

    for party in ground_truth.parties:
        if party.tax_id:
            found = normalize_tax_id(party.tax_id) in normalized
            results.append(FieldResult("tax_id", party.tax_id, found))

    if ground_truth.issue_date is not None:
        found = date_matches(text, ground_truth.issue_date)
        results.append(FieldResult("issue_date", ground_truth.issue_date.isoformat(), found))

    amounts = (
        ("total_amount", ground_truth.total_amount),
        ("net_amount", ground_truth.net_amount),
        ("tax_amount", ground_truth.tax_amount),
    )
    for field, amount in amounts:
        if amount is not None:
            found = any(v in text for v in amount_variants(amount))
            results.append(FieldResult(field, f"{amount:f}", found))

    return ReadingScore(ground_truth.invoice_id, engine, tuple(results))


def aggregate_by_engine(scores: list[ReadingScore]) -> dict[str, EngineAggregate]:
    """Combina las puntuaciones por motor: recall global y recall de identificadores fiscales."""
    by_engine: dict[str, list[ReadingScore]] = {}
    for score in scores:
        by_engine.setdefault(score.engine, []).append(score)

    aggregates: dict[str, EngineAggregate] = {}
    for engine, engine_scores in by_engine.items():
        all_fields = [r for s in engine_scores for r in s.results]
        tax_fields = [r for r in all_fields if r.field == "tax_id"]
        aggregates[engine] = EngineAggregate(
            engine=engine,
            invoices=len(engine_scores),
            recall=_ratio(all_fields),
            tax_id_recall=_ratio(tax_fields),
        )
    return aggregates


def field_recall_by_engine(scores: list[ReadingScore]) -> dict[str, dict[str, float]]:
    """Recall desglosado por tipo de campo para cada motor.

    Devuelve `{motor: {campo: recall}}` con los campos que el scorer puntúa
    (`tax_id`, `issue_date`, `total_amount`, `net_amount`, `tax_amount`). Alimenta la tabla de
    precisión por campo del informe del POC (§1.2), donde el CIF es el campo destacado (§11.8).
    """
    by_engine: dict[str, list[FieldResult]] = {}
    for score in scores:
        by_engine.setdefault(score.engine, []).extend(score.results)

    breakdown: dict[str, dict[str, float]] = {}
    for engine, fields in by_engine.items():
        per_field: dict[str, list[FieldResult]] = {}
        for result in fields:
            per_field.setdefault(result.field, []).append(result)
        breakdown[engine] = {field: _ratio(items) for field, items in per_field.items()}
    return breakdown


def _ratio(results: list[FieldResult]) -> float:
    if not results:
        return 0.0
    return sum(r.found for r in results) / len(results)

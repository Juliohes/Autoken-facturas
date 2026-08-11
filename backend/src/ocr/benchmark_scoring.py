"""Puntuación de una combinación (variante, motor) contra la verdad confirmada -- S6.7 Área B,
spec docs/specs/S6.7-benchmark-real-motor-variante.md §2/§3 (C5-C9).

Módulo PURO (sin red, sin Postgres): reutiliza `ocr.field_matching` (S6.6) para toda la
comparación campo a campo, sin duplicar ninguna lógica de parseo/normalización -- la única regla
propia de esta tarea es la tolerancia relativa del 2% en `base`/`cuota` de los tramos de IVA
(`amounts_match_within_tolerance`), nunca en el resto de campos ni en el porcentaje del tramo.

`reading`/`truth` son diccionarios con las claves de dominio ya usadas en el resto del proyecto:
`counterparty_tax_id`, `counterparty_name`, `invoice_number`, `issue_date`, `total_amount`,
`net_amount`, `tax_amount`, `tax_lines` (lista de `{iva_pct, base, cuota}` en texto).

`reading` en particular es la salida directa, NO confiable, de un motor OCR/LLM real: cualquier
campo puede llegar con un tipo JSON inesperado (lista, dict, entero...) en vez de lo que se espera
-- ver `_match_text`/`_match_date`/`_match_amount` (auditoría S6.7, hallazgo ALTO de patrones+
seguridad: ningún tipo inesperado debe llegar nunca a los comparadores de `ocr.field_matching`, que
asumen su tipo sin comprobarlo).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ocr.field_matching import (
    amounts_match,
    amounts_match_within_tolerance,
    dates_match,
    names_match,
    parse_decimal_text,
    tax_ids_match,
    tax_lines_match,
    texts_match,
)

__all__ = ["BenchmarkScore", "FieldScore", "score_combination", "TAX_LINE_TOLERANCE"]

# Tolerancia relativa exclusiva del benchmark (spec S6.7 C7): el ruido de lectura de un motor sobre
# un decimal dentro de un tramo de IVA no debe contar como fallo si el humano habría visto el mismo
# tramo. NUNCA se aplica al resto de campos (C6 sigue usando `amounts_match`, igualdad exacta).
TAX_LINE_TOLERANCE = Decimal("0.02")


def _match_text(
    matcher: Callable[[str | None, str | None], bool],
) -> Callable[[object, object], bool]:
    """Envuelve un comparador de texto (CIF, nombre, texto exacto) con la guarda de tipo que exige
    el hallazgo ALTO de la auditoría S6.7 (patrones+seguridad): `reading`/`truth` son JSON sin
    confirmar -- un tipo inesperado (lista, dict, entero...) en un campo de texto NUNCA debe llegar
    a `.strip()`/`.split()` sin comprobar antes, o revienta con un `AttributeError` sin capturar.
    Se trata como fallo real (no como "no comparable" ni como excepción), mismo criterio
    anti-alucinación que un valor no interpretable con seguridad en su tipo."""

    def _matches(reading_value: object, truth_value: object) -> bool:
        if not (reading_value is None or isinstance(reading_value, str)):
            return False
        if not (truth_value is None or isinstance(truth_value, str)):
            return False
        return matcher(reading_value, truth_value)

    return _matches


def _match_date(reading_value: object, truth_value: object) -> bool:
    """Misma guarda de tipo que `_match_text`, para el único campo de fecha (`issue_date`)."""
    if not (reading_value is None or isinstance(reading_value, str | date)):
        return False
    if not (truth_value is None or isinstance(truth_value, str | date)):
        return False
    return dates_match(reading_value, truth_value)


def _match_amount(reading_value: object, truth_value: object) -> bool:
    """Misma guarda de tipo que `_match_text`, para los 3 campos de importe escalares."""
    if not (reading_value is None or isinstance(reading_value, str | Decimal)):
        return False
    if not (truth_value is None or isinstance(truth_value, str | Decimal)):
        return False
    return amounts_match(reading_value, truth_value)


# Los 7 campos escalares puntuables (mismo orden/nombres que S4.8/S6.6), cada uno envuelto con su
# propia guarda de tipo -- nunca se llama a un comparador de `ocr.field_matching` con un valor de
# tipo inesperado (ver docstring del módulo).
_SCALAR_FIELD_MATCHERS: dict[str, Callable[[object, object], bool]] = {
    "counterparty_tax_id": _match_text(tax_ids_match),
    "counterparty_name": _match_text(names_match),
    "invoice_number": _match_text(texts_match),
    "issue_date": _match_date,
    "total_amount": _match_amount,
    "net_amount": _match_amount,
    "tax_amount": _match_amount,
}


@dataclass(frozen=True)
class FieldScore:
    """Resultado de comparar un único campo escalar -- `match=None` significa "no comparable"
    (verdad ausente, spec C5), nunca "no puntuado por descuido"."""

    field: str
    match: bool | None


@dataclass(frozen=True)
class BenchmarkScore:
    """Puntuación completa de una combinación (variante, motor) sobre una factura: el desglose por
    campo (C9, necesario para el ranking por grupo, §6.2 de la spec) más el ratio agregado."""

    field_scores: tuple[FieldScore, ...]
    tax_lines_matched: bool | None
    aciertos: int
    comparables: int


def _parse_tax_line_amount(value: object) -> Decimal | None:
    """Interpreta `base`/`cuota` de un tramo de IVA como `Decimal`, o `None` si no se puede hacer
    con seguridad (mismo criterio anti-alucinación que `ocr.field_matching._parse_amount`, pero sin
    su guarda de coma ambigua: aquí los tramos siempre llegan ya en texto con punto/coma simple
    desde `ocr.analysis`, nunca tecleados a mano por un humano). Reutiliza
    `ocr.field_matching.parse_decimal_text` para el `try/except Decimal` en sí, sin reimplementarlo
    (S6.7 auditoría, hallazgo de SOLID -- símbolo público desde la ronda 3 de la auditoría, ya no
    con guion bajo: tiene este consumidor externo declarado)."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return parse_decimal_text(str(value).strip().replace(",", "."))


def _parse_tax_lines(
    tax_lines: object,
) -> list[tuple[str | None, Decimal | None, Decimal | None]]:
    """Convierte `[{"iva_pct": ..., "base": ..., "cuota": ...}, ...]` al formato que espera
    `ocr.field_matching.tax_lines_match` (tuplas `(iva_pct, base, cuota)`)."""
    if not isinstance(tax_lines, list):
        return []
    parsed: list[tuple[str | None, Decimal | None, Decimal | None]] = []
    for line in tax_lines:
        if not isinstance(line, Mapping):
            continue
        iva_pct = line.get("iva_pct")
        parsed.append(
            (
                str(iva_pct) if iva_pct is not None else None,
                _parse_tax_line_amount(line.get("base")),
                _parse_tax_line_amount(line.get("cuota")),
            )
        )
    return parsed


def _tolerant_amount_matcher(a: Decimal | None, b: Decimal | None) -> bool:
    return amounts_match_within_tolerance(a, b, tolerance=TAX_LINE_TOLERANCE)


def _score_tax_lines(reading: Mapping[str, object], truth: Mapping[str, object]) -> bool | None:
    """Puntúa el grupo "Tramos IVA" como un único ítem -- `None` si la verdad no tiene ningún tramo
    (sin verdad no se puntúa, mismo criterio general de C5; caso no cubierto por un test explícito
    de la spec pero coherente con ella) O si `truth["tax_lines"]` no es siquiera una lista (dato
    corrupto: nunca se descarta en silencio a `[]` -- eso haría que `tax_lines_match([], [])`
    puntuara como acierto por vacuidad con datos de verdad corruptos, en vez de "no comparable";
    auditoría S6.7, hallazgo de patrones+seguridad)."""
    truth_lines_raw = truth.get("tax_lines")
    if not isinstance(truth_lines_raw, list) or not truth_lines_raw:
        return None
    reading_lines = _parse_tax_lines(reading.get("tax_lines"))
    truth_lines = _parse_tax_lines(truth_lines_raw)
    return tax_lines_match(reading_lines, truth_lines, amount_matcher=_tolerant_amount_matcher)


def score_combination(reading: Mapping[str, object], truth: Mapping[str, object]) -> BenchmarkScore:
    """Puntúa una lectura (de una combinación variante×motor) contra la verdad confirmada.

    Un campo con verdad ausente (`None`/cadena vacía) no cuenta en `comparables` (C5). Un campo con
    verdad presente pero no leído por el motor (`reading[field] is None`) SÍ es comparable y cuenta
    como fallo real -- anti-alucinación, nunca se descarta como "no comparable" solo porque el motor
    no lo leyó. Un campo con verdad presente pero leído por el motor con un tipo JSON inesperado
    (lista, dict, entero...) también cuenta como fallo real, nunca lanza (ver `_match_text`/
    `_match_date`/`_match_amount`).
    """
    field_scores: list[FieldScore] = []
    aciertos = 0
    comparables = 0

    for field, matcher in _SCALAR_FIELD_MATCHERS.items():
        truth_value = truth.get(field)
        if truth_value is None or truth_value == "":
            field_scores.append(FieldScore(field=field, match=None))
            continue
        reading_value = reading.get(field)
        matched = matcher(reading_value, truth_value)
        field_scores.append(FieldScore(field=field, match=matched))
        comparables += 1
        if matched:
            aciertos += 1

    tax_lines_result = _score_tax_lines(reading, truth)
    if tax_lines_result is not None:
        comparables += 1
        if tax_lines_result:
            aciertos += 1

    return BenchmarkScore(
        field_scores=tuple(field_scores),
        tax_lines_matched=tax_lines_result,
        aciertos=aciertos,
        comparables=comparables,
    )

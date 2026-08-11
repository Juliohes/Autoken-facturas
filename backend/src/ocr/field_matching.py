"""Comparación tipada compartida de un campo de factura (S6.6, spec
docs/specs/S6.6-laboratorio-comparacion-honesta.md, Área A / C1-C2).

Punto único del proyecto que decide "¿coinciden estos dos valores del mismo campo?", por tipo de
dato: importe (igualdad decimal tras normalizar coma/punto), fecha (igualdad de `date`), CIF/NIF
(igualdad tras `shared.tax_id.normalize_tax_id`), nombre de contraparte (igualdad tras colapsar
espacios, SIN tocar mayúsculas) y texto exacto (número de factura y similares, sin normalizar en
absoluto). Reutilizado por `invoicing.corrections` (C3, extracción pura sin cambio de
comportamiento) y por el benchmark de S6.7.

Contrato común a las 5 funciones (spec §4, invariantes):
- `None` contra `None` -> `True` (nada que objetar; "no comparable" lo decide quien llama, no esta
  capa -- spec C8).
- Un lado `None` y el otro con valor -> `False`.
- Un valor que no se puede interpretar con seguridad en su tipo (texto no numérico en un importe,
  fecha con formato inválido, una coma ambigua de miles) NUNCA cuenta como acierto, ni siquiera
  comparado contra la misma basura repetida -- anti-alucinación, nunca se arriesga una conversión a
  ciegas.

Modo adicional, exclusivo de S6.7 (spec docs/specs/S6.7-benchmark-real-motor-variante.md, C7/C8):
`amounts_match_within_tolerance` + el parámetro `amount_matcher` de `tax_lines_match` permiten una
coincidencia CON tolerancia relativa (el benchmark de motores necesita distinguir "ruido de lectura
aceptable" de "fallo real" en `base`/`cuota` de un tramo de IVA). Es un modo opt-in: por defecto
`tax_lines_match` sigue exigiendo igualdad EXACTA (`amounts_match`), el contrato de S6.6 no cambia
para ningún llamante existente. `ocr.benchmark_scoring` es hoy el único consumidor de la tolerancia
(auditoría S6.7, hallazgo de arquitectura: se decidió mantenerla aquí -- junto al resto de
comparadores del mismo campo, en vez de trasladarla a `benchmark_scoring` -- por ser más simple
dado que `tax_lines_match` ya vive en este módulo y la tolerancia es solo un parámetro más de su
firma, sin ningún import cruzado nuevo).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from datetime import date
from decimal import Decimal, InvalidOperation

from shared.tax_id import normalize_tax_id

__all__ = [
    "amounts_match",
    "amounts_match_within_tolerance",
    "dates_match",
    "format_value",
    "group_tax_lines_by_pct",
    "names_match",
    "parse_decimal_text",
    "tax_ids_match",
    "tax_lines_match",
    "texts_match",
]

# Una coma seguida de 1-2 dígitos es inequívocamente decimal ("21,45"); 3+ dígitos son ambiguos
# (¿decimal de 3 cifras real, o una coma de miles tecleada por error, ej. "1,234" queriendo decir
# 1234?) -- misma regla anti-ambigüedad que el frontend (`shared/format.ts`, hallazgo de auditoría
# S6.1, 2026-08-08), reimplementada aquí en Python para el mismo criterio en el backend.
_UNAMBIGUOUS_COMMA_DECIMAL = re.compile(r"^-?\d+,\d{1,2}$")


def parse_decimal_text(trimmed: str) -> Decimal | None:
    """Interpreta un texto YA normalizado (separador decimal en punto) como `Decimal`, o `None` si
    no es un decimal válido -- pieza base compartida por `_parse_amount` (que añade la guarda
    anti-ambigüedad de coma de miles antes de llegar aquí) y por
    `ocr.benchmark_scoring._parse_tax_line_amount` (que reemplaza toda coma por punto sin esa
    guarda: los tramos de IVA del benchmark siempre llegan ya en texto desde `ocr.analysis`, nunca
    tecleados a mano -- S6.7 auditoría, hallazgo de SOLID, para no reimplementar este mismo
    `try/except Decimal` dos veces).

    Símbolo público a propósito (sin guion bajo, en `__all__`): tiene un consumidor fuera de este
    módulo (`ocr.benchmark_scoring`) -- auditoría S6.7, ronda 3, hallazgo de SOLID+arquitectura: un
    nombre "privado" con un import cruzado real rompe la encapsulación sin ningún aviso de que
    tiene un consumidor externo.

    Nota: `Decimal()` acepta con éxito textos como `"nan"`/`"NaN"`/`"Infinity"` (no son un error de
    parseo) -- el llamante es responsable de rechazar un resultado no finito ANTES de operar con él
    (ver `amounts_match_within_tolerance`, S6.7 auditoría ronda 3, hallazgo ALTO)."""
    try:
        return Decimal(trimmed)
    except InvalidOperation:
        return None


def _parse_amount(value: str | Decimal) -> Decimal | None:
    """Interpreta un importe como `Decimal`, o `None` si no se puede hacer con seguridad."""
    if isinstance(value, Decimal):
        return value
    trimmed = value.strip()
    if _UNAMBIGUOUS_COMMA_DECIMAL.match(trimmed):
        trimmed = trimmed.replace(",", ".")
    return parse_decimal_text(trimmed)


def amounts_match(a: str | Decimal | None, b: str | Decimal | None) -> bool:
    """Dos importes coinciden si tienen el mismo valor decimal, sin importar el formato de texto
    (coma/punto, ceros de más) -- spec C1.

    Un `NaN`/`Infinity` NO necesita la misma guarda que `amounts_match_within_tolerance` (S6.7
    auditoría, ronda 3, verificado con un test dedicado antes de decidir): esta función solo hace
    `==`, que nunca lanza con un `Decimal` no finito (`NaN == NaN` da `False`, `Infinity ==
    Infinity` da `True`, ninguno de los dos revienta). El único caso en que "coincidiría" sería
    ambos lados literalmente `Infinity`, algo que nunca ocurre con datos reales de una factura
    confirmada (la verdad nunca es infinita) -- riesgo teórico, no un bug observable, y fuera del
    hallazgo concreto de esta ronda (que es sobre la división en la tolerancia)."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    parsed_a, parsed_b = _parse_amount(a), _parse_amount(b)
    if parsed_a is None or parsed_b is None:
        return False
    return parsed_a == parsed_b


def amounts_match_within_tolerance(
    a: str | Decimal | None, b: str | Decimal | None, *, tolerance: Decimal
) -> bool:
    """Como `amounts_match`, pero admite una diferencia relativa `<= tolerance` como acierto --
    exclusiva del benchmark de S6.7 (tramos de IVA, C7/C8), nunca usada por S6.6.

    Dos valores idénticos siempre coinciden, aunque `tolerance=0` (spec S6.7 C7). El caso "0 vs 0"
    ya lo resuelve esa misma igualdad exacta (`Decimal("0.00") == Decimal("0")` es `True` en
    Python, sin importar la escala) -- no hace falta ninguna guarda aparte para "ambos son 0"
    (auditoría S6.7, ronda 3, hallazgo de SOLID: la guarda `largest == 0` que hubo aquí antes era
    código inalcanzable, retirada).

    Un `NaN`/`Infinity` (`Decimal()` los acepta al parsear sin error, pero no son valores seguros
    para operar) NUNCA cuenta como acierto, ni siquiera comparado consigo mismo -- mismo criterio
    anti-alucinación que el resto del módulo (auditoría S6.7, ronda 3, hallazgo ALTO de patrones+
    seguridad: un motor OCR/LLM puede alucinar el texto `"nan"`/`"Infinity"` en `base`/`cuota` de
    un tramo de IVA, JSON perfectamente válido pero dato de entrada no confiable; sin esta guarda,
    `max(abs(parsed_a), abs(parsed_b))` revienta con `decimal.InvalidOperation` en cuanto uno de
    los dos lados es `NaN`). Por eso esta comprobación va ANTES del atajo de igualdad exacta:
    `Decimal("Infinity") == Decimal("Infinity")` es `True` sin lanzar, y contaría como acierto por
    "coincidir consigo mismo" si se dejara pasar."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    parsed_a, parsed_b = _parse_amount(a), _parse_amount(b)
    if parsed_a is None or parsed_b is None:
        return False
    if not parsed_a.is_finite() or not parsed_b.is_finite():
        return False
    if parsed_a == parsed_b:
        return True
    relative_difference = abs(parsed_a - parsed_b) / max(abs(parsed_a), abs(parsed_b))
    return relative_difference <= tolerance


def _parse_date(value: str | date) -> date | None:
    """Interpreta una fecha ISO (`YYYY-MM-DD`), o `None` si el formato no es válido."""
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def dates_match(a: str | date | None, b: str | date | None) -> bool:
    """Dos fechas coinciden si representan el mismo día, sin importar si llegan como texto ISO o
    `date` ya tipado."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    parsed_a, parsed_b = _parse_date(a), _parse_date(b)
    if parsed_a is None or parsed_b is None:
        return False
    return parsed_a == parsed_b


def tax_ids_match(a: str | None, b: str | None) -> bool:
    """Dos CIF/NIF coinciden tras `shared.tax_id.normalize_tax_id` (mayúsculas, sin separadores) --
    spec C2, mismo criterio ya usado en el resto del proyecto."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    normalized_a = normalize_tax_id(a) or None
    normalized_b = normalize_tax_id(b) or None
    if normalized_a is None or normalized_b is None:
        return False
    return normalized_a == normalized_b


def names_match(a: str | None, b: str | None) -> bool:
    """Dos nombres de contraparte coinciden tras colapsar espacios sobrantes -- a diferencia del
    CIF, las mayúsculas NO se normalizan a propósito: un cambio real de capitalización cuenta como
    una diferencia real."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return " ".join(a.split()) == " ".join(b.split())


def texts_match(a: str | None, b: str | None) -> bool:
    """Comparación EXACTA sin normalizar (número de factura y similares): ni espacios ni
    mayúsculas se tocan, para no introducir un cambio de comportamiento silencioso."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return a == b


def format_value(value: object | None) -> str | None:
    """Representación textual estable de un valor para `ai_value`/`human_value` (S2.5) y para las
    columnas del laboratorio (S6.2/S6.6).

    Movida aquí desde `invoicing.corrections` (2026-08-11, S6.6 auditoría, hallazgo de
    arquitectura): `platform_admin.lab_service` ya la necesitaba y S6.7 también la necesitará desde
    el contexto `ocr` -- dejarla en `invoicing` habría forzado a `ocr` a depender de `invoicing`,
    violando la dirección de dependencias del proyecto (`ocr` solo depende de `shared`).
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


# El parámetro de tipo genérico `PctT` (en vez de fijar `Decimal` o `Decimal | None`) permite que
# cada llamante conserve su propio tipo de `iva_pct`: `invoicing.corrections.TaxLineFields.iva_pct`
# es `Decimal` a secas (nunca `None` en ese dataclass), mientras que
# `invoicing_repository.InvoiceRecord.tax_lines` tipa el tramo tal cual sale de la fila SQL, con
# `iva_pct: Decimal | None`. Fijar un único tipo aquí habría forzado a uno de los dos llamantes a
# mentir sobre su propio tipo real.
def group_tax_lines_by_pct[PctT](
    lines: Iterable[tuple[PctT, Decimal | None, Decimal | None]],
) -> dict[PctT, tuple[Decimal | None, Decimal | None]]:
    """Agrupa tramos de IVA `(iva_pct, base, cuota)` por tipo de IVA, para emparejar OCR vs
    confirmado por tramo -- fuente única del algoritmo de agrupación, reutilizada por
    `invoicing.corrections._diff_tax_lines` (necesita el detalle por tramo, altas/bajas) y por
    `tax_lines_match` (solo necesita el booleano del conjunto)."""
    return {iva_pct: (base, cuota) for iva_pct, base, cuota in lines}


def tax_lines_match[PctT](
    baseline: Iterable[tuple[PctT, Decimal | None, Decimal | None]],
    confirmed: Iterable[tuple[PctT, Decimal | None, Decimal | None]],
    *,
    amount_matcher: Callable[[Decimal | None, Decimal | None], bool] = amounts_match,
) -> bool:
    """El conjunto de tramos de IVA coincide -- spec S6.6 C9: mismo número de tramos, mismos tipos
    de IVA presentes, y `base`/`cuota` coinciden por valor (`amounts_match` por defecto, no `==`
    crudo de `Decimal`) tramo a tramo.

    `amount_matcher` permite sustituir la comparación de `base`/`cuota` (p. ej. por
    `amounts_match_within_tolerance` con un 2% de margen, S6.7 C7) sin duplicar el algoritmo de
    emparejamiento por `iva_pct` -- la tasa/porcentaje sigue exigiendo coincidencia EXACTA por
    clave del `dict`, nunca pasa por `amount_matcher` (S6.7 C8)."""
    baseline_lines = list(baseline)
    confirmed_lines = list(confirmed)
    if len(baseline_lines) != len(confirmed_lines):
        return False
    by_pct_baseline = group_tax_lines_by_pct(baseline_lines)
    by_pct_confirmed = group_tax_lines_by_pct(confirmed_lines)
    if set(by_pct_baseline) != set(by_pct_confirmed):
        return False
    return all(
        amount_matcher(by_pct_baseline[pct][0], by_pct_confirmed[pct][0])
        and amount_matcher(by_pct_baseline[pct][1], by_pct_confirmed[pct][1])
        for pct in by_pct_baseline
    )

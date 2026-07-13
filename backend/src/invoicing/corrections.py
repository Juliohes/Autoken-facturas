"""Diff puro OCR vs confirmado (S2.5): qué campos cambió el humano respecto a lo que leyó la IA.

Módulo sin efectos: recibe el baseline del OCR (S2.3) y los valores confirmados y devuelve una
`Correction` por cada campo que DIFIERE. El baseline es lo que persistió el OCR, nunca lo que mande
el cliente (spec §4). La comparación es por tipo (spec): `Decimal` para importes, `date` para la
fecha, CIF normalizado y nombre con espacios colapsados. Los valores se guardan como texto
(`ai_value`/`human_value`).

Se comparan los campos escalares de la factura (fecha, importes, CIF y nombre de contraparte). Los
tramos de IVA (`tax_lines`) NO generan corrección todavía: requieren un emparejamiento por tipo de
IVA entre el OCR (`[{base, rate, cuota}]`) y la confirmación (`[{iva_pct, base, cuota}]`) que se
aborda por separado; hasta entonces su valor confirmado se persiste en `invoice_tax_lines`, no en el
dataset de correcciones. Ver issue #70.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from shared.tax_id import normalize_tax_id


@dataclass(frozen=True)
class Correction:
    """Un campo cuyo valor confirmado difiere del que leyó el OCR (fila de `ocr_corrections`)."""

    field: str
    ai_value: str | None
    human_value: str | None


@dataclass(frozen=True)
class ConfirmedFields:
    """Valores escalares confirmados por el humano, tipados, para comparar con el baseline OCR."""

    issue_date: date | None
    total_amount: Decimal | None
    net_amount: Decimal | None
    tax_amount: Decimal | None
    counterparty_tax_id: str | None
    counterparty_name: str | None


@dataclass(frozen=True)
class BaselineFields:
    """Valores escalares que persistió el OCR (S2.3): el baseline del diff."""

    issue_date: date | None
    total_amount: Decimal | None
    net_amount: Decimal | None
    tax_amount: Decimal | None
    counterparty_tax_id: str | None
    counterparty_name: str | None


def _norm_name(value: str | None) -> str | None:
    """Normaliza un nombre para comparar: sin espacios sobrantes (colapsa y recorta)."""
    if value is None:
        return None
    return " ".join(value.split())


def _norm_cif(value: str | None) -> str | None:
    """Normaliza un CIF para comparar (mayúsculas, sin separadores); vacío -> None."""
    if value is None:
        return None
    canonical = normalize_tax_id(value)
    return canonical or None


def _text(value: object | None) -> str | None:
    """Representación textual estable de un valor para `ai_value`/`human_value`."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def diff_corrections(baseline: BaselineFields, confirmed: ConfirmedFields) -> list[Correction]:
    """Devuelve una `Correction` por campo cuyo valor confirmado difiere del baseline del OCR.

    Igualdad por tipo: importes con `Decimal` (121.00 == 121.0), fecha con `date`, CIF y nombre
    normalizados. Un campo igual NO genera corrección. Cuando difieren, `ai_value` es el valor del
    OCR y `human_value` el confirmado, ambos como texto (el valor CRUDO, no el normalizado).
    """
    corrections: list[Correction] = []

    def add(field: str, ai: object | None, human: object | None) -> None:
        corrections.append(Correction(field=field, ai_value=_text(ai), human_value=_text(human)))

    if baseline.issue_date != confirmed.issue_date:
        add("issue_date", baseline.issue_date, confirmed.issue_date)
    if baseline.net_amount != confirmed.net_amount:
        add("net_amount", baseline.net_amount, confirmed.net_amount)
    if baseline.tax_amount != confirmed.tax_amount:
        add("tax_amount", baseline.tax_amount, confirmed.tax_amount)
    if baseline.total_amount != confirmed.total_amount:
        add("total_amount", baseline.total_amount, confirmed.total_amount)
    if _norm_cif(baseline.counterparty_tax_id) != _norm_cif(confirmed.counterparty_tax_id):
        add("counterparty_tax_id", baseline.counterparty_tax_id, confirmed.counterparty_tax_id)
    if _norm_name(baseline.counterparty_name) != _norm_name(confirmed.counterparty_name):
        add("counterparty_name", baseline.counterparty_name, confirmed.counterparty_name)

    return corrections

"""Diff puro OCR vs confirmado (S2.5): qué campos cambió el humano respecto a lo que leyó la IA.

Módulo sin efectos: recibe el baseline del OCR (S2.3) y los valores confirmados y devuelve una
`Correction` por cada campo que DIFIERE. El baseline es lo que persistió el OCR, nunca lo que mande
el cliente (spec §4). La comparación es por tipo (spec): `Decimal` para importes, `date` para la
fecha, CIF normalizado y nombre con espacios colapsados. Los valores se guardan como texto
(`ai_value`/`human_value`).

Se comparan los campos escalares de la factura (fecha, importes, CIF y nombre de contraparte) y los
**tramos de IVA**: se emparejan por tipo de IVA (`iva_pct`) entre el OCR y la confirmación, y se
registra una corrección por `base`/`cuota` que difiere, más las altas/bajas de tramo (issue #70).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ocr.field_matching import (
    amounts_match,
    dates_match,
    format_value,
    group_tax_lines_by_pct,
    names_match,
    tax_ids_match,
    texts_match,
)
from shared.diffing import Correction as Correction

# `Correction` vivía aquí; movida a `shared.diffing` (2026-08-01) para que `companies` pueda
# reutilizarla sin invertir la dirección de dependencias (`invoicing -> companies`). Re-exportada
# tal cual: los imports existentes (`from invoicing.corrections import Correction`) siguen
# funcionando sin cambios.


@dataclass(frozen=True)
class TaxLineFields:
    """Un tramo de IVA para el diff: tipo (`iva_pct`) + base + cuota, tipados."""

    iva_pct: Decimal
    base: Decimal
    cuota: Decimal


@dataclass(frozen=True)
class ConfirmedFields:
    """Valores confirmados por el humano, tipados, para comparar con el baseline OCR."""

    issue_date: date | None
    total_amount: Decimal | None
    net_amount: Decimal | None
    tax_amount: Decimal | None
    counterparty_tax_id: str | None
    counterparty_name: str | None
    invoice_number: str | None = None
    tax_lines: tuple[TaxLineFields, ...] = ()


@dataclass(frozen=True)
class BaselineFields:
    """Valores que persistió el OCR (S2.3): el baseline del diff."""

    issue_date: date | None
    total_amount: Decimal | None
    net_amount: Decimal | None
    tax_amount: Decimal | None
    counterparty_tax_id: str | None
    counterparty_name: str | None
    invoice_number: str | None = None
    tax_lines: tuple[TaxLineFields, ...] = ()


def diff_corrections(baseline: BaselineFields, confirmed: ConfirmedFields) -> list[Correction]:
    """Devuelve una `Correction` por campo cuyo valor confirmado difiere del baseline del OCR.

    Igualdad por tipo: importes con `Decimal` (121.00 == 121.0), fecha con `date`, CIF y nombre
    normalizados. Un campo igual NO genera corrección. Cuando difieren, `ai_value` es el valor del
    OCR y `human_value` el confirmado, ambos como texto (el valor CRUDO, no el normalizado).
    """
    corrections: list[Correction] = []

    def add(field: str, ai: object | None, human: object | None) -> None:
        corrections.append(
            Correction(field=field, ai_value=format_value(ai), human_value=format_value(human))
        )

    if not dates_match(baseline.issue_date, confirmed.issue_date):
        add("issue_date", baseline.issue_date, confirmed.issue_date)
    if not amounts_match(baseline.net_amount, confirmed.net_amount):
        add("net_amount", baseline.net_amount, confirmed.net_amount)
    if not amounts_match(baseline.tax_amount, confirmed.tax_amount):
        add("tax_amount", baseline.tax_amount, confirmed.tax_amount)
    if not amounts_match(baseline.total_amount, confirmed.total_amount):
        add("total_amount", baseline.total_amount, confirmed.total_amount)
    if not tax_ids_match(baseline.counterparty_tax_id, confirmed.counterparty_tax_id):
        add("counterparty_tax_id", baseline.counterparty_tax_id, confirmed.counterparty_tax_id)
    if not names_match(baseline.counterparty_name, confirmed.counterparty_name):
        add("counterparty_name", baseline.counterparty_name, confirmed.counterparty_name)
    if not texts_match(baseline.invoice_number, confirmed.invoice_number):  # spec: S6.1 C5
        add("invoice_number", baseline.invoice_number, confirmed.invoice_number)

    _diff_tax_lines(baseline.tax_lines, confirmed.tax_lines, add)
    return corrections


def _pct_label(pct: Decimal) -> str:
    """Etiqueta canónica del tipo de IVA para el nombre del campo (21, no 21.00)."""
    normalized = pct.normalize()
    # `normalize()` de un entero da notación exponencial (2E+1); `quantize` a entero lo evita.
    return str(
        normalized.quantize(Decimal(1)) if normalized == normalized.to_integral() else normalized
    )


def _diff_tax_lines(
    baseline: tuple[TaxLineFields, ...],
    confirmed: tuple[TaxLineFields, ...],
    add: Callable[[str, object | None, object | None], None],
) -> None:
    """Empareja tramos por `iva_pct` y registra la corrección de `base`/`cuota` que difiere.

    Un tramo presente solo en la confirmación es un alta (ai `None`); solo en el OCR, una baja
    (human `None`). El nombre del campo lleva el tipo de IVA: `tax_line[21].base`.
    """
    by_pct_base = group_tax_lines_by_pct((line.iva_pct, line.base, line.cuota) for line in baseline)
    by_pct_conf = group_tax_lines_by_pct(
        (line.iva_pct, line.base, line.cuota) for line in confirmed
    )
    for pct in sorted(set(by_pct_base) | set(by_pct_conf)):
        label = _pct_label(pct)
        base_ai, cuota_ai = by_pct_base.get(pct, (None, None))
        base_human, cuota_human = by_pct_conf.get(pct, (None, None))
        if base_ai != base_human:
            add(f"tax_line[{label}].base", base_ai, base_human)
        if cuota_ai != cuota_human:
            add(f"tax_line[{label}].cuota", cuota_ai, cuota_human)

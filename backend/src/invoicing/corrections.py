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

from shared.diffing import Correction as Correction
from shared.tax_id import normalize_tax_id

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
    tax_lines: tuple[TaxLineFields, ...] = ()


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
    by_pct_base: dict[Decimal, tuple[Decimal | None, Decimal | None]] = {
        line.iva_pct: (line.base, line.cuota) for line in baseline
    }
    by_pct_conf: dict[Decimal, tuple[Decimal | None, Decimal | None]] = {
        line.iva_pct: (line.base, line.cuota) for line in confirmed
    }
    for pct in sorted(set(by_pct_base) | set(by_pct_conf)):
        label = _pct_label(pct)
        base_ai, cuota_ai = by_pct_base.get(pct, (None, None))
        base_human, cuota_human = by_pct_conf.get(pct, (None, None))
        if base_ai != base_human:
            add(f"tax_line[{label}].base", base_ai, base_human)
        if cuota_ai != cuota_human:
            add(f"tax_line[{label}].cuota", cuota_ai, cuota_human)

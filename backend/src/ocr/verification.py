"""Verificación determinista "tipo DNI" de datos de factura (ADR-0010).

Los campos numéricos clave de una factura (NIF/NIE/CIF, IBAN, importes) NO dependen de
que la IA los "lea bien": se verifican con algoritmos deterministas —dígitos de control y
cuadre aritmético—, igual que el lector de un DNI valida su dígito de control. Un valor que
el OCR lea mal y rompa el dígito de control se detecta y se marca para revisión, en lugar de
darse por bueno y llegar a contabilidad como si fuera correcto (regla anti-alucinación).

Los validadores estructurales de identificadores fiscales e IBAN son un primitivo de dominio
general y viven en `shared.tax_id` (los comparten `companies`/`identity`). Esta capa es la
verificación OCR de una factura: reexporta esos validadores para sus llamadores y añade el
**cuadre aritmético** (base x IVA% = cuota, y Σbases + ΣIVA − IRPF = total), que sí es propio
de la factura. Módulo puro y sin dependencias externas; la comprobación online contra VIES/AEAT
vive en otra capa porque requiere red.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel

# El primitivo de validación fiscal/IBAN vive en `shared.tax_id`. Se reexporta aquí para no romper
# los llamadores históricos de la capa OCR (`from ocr.verification import validate_tax_id, ...`).
from shared.tax_id import (
    CheckResult,
    normalize_tax_id,
    validate_cif,
    validate_iban,
    validate_nie,
    validate_nif,
    validate_tax_id,
)

__all__ = [
    "CheckResult",
    "TaxLine",
    "validate_nif",
    "validate_nie",
    "validate_cif",
    "validate_tax_id",
    "normalize_tax_id",
    "validate_iban",
    "check_tax_line",
    "check_invoice_totals",
    "TaxLineCheck",
    "InvoiceMathCheck",
    "check_invoice_totals_detailed",
    "DEFAULT_MONEY_TOLERANCE",
]

# Tolerancia por defecto (en euros) para el cuadre aritmético: absorbe redondeos legales.
DEFAULT_MONEY_TOLERANCE = Decimal("0.02")
# Base de un porcentaje: un tipo de IVA del 21% es 21/100 de la base.
_PERCENT_BASE = Decimal(100)


# --- Cuadre aritmético ---------------------------------------------------------------------


@dataclass(frozen=True)
class TaxLine:
    """Un tramo de impuesto de la factura: base imponible, tipo de IVA % y cuota de IVA.

    Value object inmutable con campos nombrados para no confundir el orden de los importes.
    Modela solo `(base, iva_pct, cuota)`; recargo de equivalencia, IRPF por línea y
    descripción/número de línea quedan fuera de alcance (se añadirán sin romper llamadores).
    """

    base: Decimal
    iva_pct: Decimal
    cuota: Decimal


class TaxLineCheck(BaseModel):
    """Diagnóstico de un tramo de IVA, además del veredicto global histórico."""

    index: int
    expected_quota: Decimal
    actual_quota: Decimal
    delta: Decimal
    valid: bool


class InvoiceMathCheck(BaseModel):
    """Diagnóstico completo del cuadre de una factura."""

    line_checks: list[TaxLineCheck]
    expected_total: Decimal | None
    actual_total: Decimal | None
    total_delta: Decimal | None
    valid: bool | None
    reasons: list[str]


def _is_finite(*values: Decimal) -> bool:
    """True solo si TODOS los importes son `Decimal` finitos (ni NaN ni Infinity).

    Guarda explícita anti-alucinación: el veredicto de finitud no puede depender del
    estado global mutable (los traps del contexto decimal). Por eso se interroga cada
    valor con `.is_nan()`/`.is_infinite()` en lugar de confiar en que una operación lance.
    """
    return all(not value.is_nan() and not value.is_infinite() for value in values)


def _within_tolerance(expected: Decimal, actual: Decimal, tolerance: Decimal) -> bool:
    """Único punto que define "cuadrar": la diferencia absoluta cabe en la tolerancia."""
    return abs(expected - actual) <= tolerance


def check_tax_line(
    base: Decimal,
    iva_pct: Decimal,
    cuota: Decimal,
    *,
    tolerance: Decimal = DEFAULT_MONEY_TOLERANCE,
) -> CheckResult:
    """Comprueba que base x IVA% = cuota (con tolerancia de redondeo)."""
    if not _is_finite(base, iva_pct, cuota):
        return CheckResult(False, "Importe no numérico/no finito (NaN o Infinity)")
    expected = base * iva_pct / _PERCENT_BASE
    if not _within_tolerance(expected, cuota, tolerance):
        return CheckResult(
            False,
            f"Descuadre: {base} x {iva_pct}% = {expected}, pero cuota declarada {cuota}",
        )
    return CheckResult(True)


def _check_global_sum(
    lines: list[TaxLine],
    total: Decimal,
    irpf_cuota: Decimal,
    tolerance: Decimal,
) -> CheckResult:
    """Cuadre global de la suma: Σbases + Σcuotas IVA − IRPF = total (con tolerancia).

    Helper PRIVADO: el cuadre global aislado nunca es punto de entrada público, para no
    reabrir el agujero anti-alucinación (validar el total sin validar cada tramo).
    """
    # Las bases/cuotas ya vienen validadas por tramo; aquí solo falta blindar `total`.
    if not _is_finite(total):
        return CheckResult(False, "Total no numérico/no finito (NaN o Infinity)")
    sum_base = sum((line.base for line in lines), Decimal(0))
    sum_iva = sum((line.cuota for line in lines), Decimal(0))
    expected = sum_base + sum_iva - irpf_cuota
    if not _within_tolerance(expected, total, tolerance):
        return CheckResult(
            False,
            f"Descuadre de total: Σbases {sum_base} + ΣIVA {sum_iva} − IRPF {irpf_cuota} "
            f"= {expected}, pero total declarado {total}",
        )
    return CheckResult(True)


def check_invoice_totals(
    lines: list[TaxLine],
    total: Decimal,
    *,
    irpf_cuota: Decimal = Decimal(0),
    tolerance: Decimal = DEFAULT_MONEY_TOLERANCE,
) -> CheckResult:
    """Verifica el cuadre de una factura: cada tramo y el cuadre global del total.

    Primero comprueba cada tramo (`base x IVA% = cuota`); al PRIMER tramo que no cuadre
    (fail-fast) devuelve el motivo identificando ese tramo (numeración 1-based). Si todos
    los tramos cuadran, comprueba el cuadre global `Σbases + Σcuotas IVA − IRPF = total`.

    `irpf_cuota` es la retención a descontar. La tolerancia absorbe redondeos en ambos niveles.
    """
    for index, line in enumerate(lines, start=1):
        # Cuadre de tramo: la cuota debe derivarse de base e IVA% (regla anti-alucinación).
        line_result = check_tax_line(line.base, line.iva_pct, line.cuota, tolerance=tolerance)
        if not line_result.valid:
            return CheckResult(False, f"Tramo {index}: {line_result.reason}")
    return _check_global_sum(lines, total, irpf_cuota, tolerance)


def check_invoice_totals_detailed(
    lines: list[TaxLine],
    total: Decimal | None,
    *,
    irpf_cuota: Decimal = Decimal(0),
    tolerance: Decimal = DEFAULT_MONEY_TOLERANCE,
) -> InvoiceMathCheck:
    """Devuelve el detalle por tramo sin cambiar el `CheckResult` histórico."""
    line_checks: list[TaxLineCheck] = []
    reasons: list[str] = []
    all_finite = _is_finite(irpf_cuota) and all(
        _is_finite(line.base, line.iva_pct, line.cuota) for line in lines
    )
    for index, line in enumerate(lines, start=1):
        if not _is_finite(line.base, line.iva_pct, line.cuota):
            line_checks.append(
                TaxLineCheck(
                    index=index,
                    expected_quota=Decimal(0),
                    actual_quota=Decimal(0),
                    delta=Decimal(0),
                    valid=False,
                )
            )
            reasons.append(f"tax_line_{index}_non_finite")
            continue
        expected = line.base * line.iva_pct / _PERCENT_BASE
        delta = line.cuota - expected
        line_valid = _within_tolerance(expected, line.cuota, tolerance)
        line_checks.append(
            TaxLineCheck(
                index=index,
                expected_quota=expected,
                actual_quota=line.cuota,
                delta=delta,
                valid=line_valid,
            )
        )
        if not line_valid:
            reasons.append(f"tax_line_{index}_mismatch")

    expected_total: Decimal | None = None
    actual_total = total if total is not None and _is_finite(total) else None
    total_delta: Decimal | None = None
    if not all_finite:
        reasons.append("non_finite_value")
    elif total is not None:
        expected_total = sum((line.base + line.cuota for line in lines), Decimal(0)) - irpf_cuota
        total_delta = total - expected_total
        if not _within_tolerance(expected_total, total, tolerance):
            reasons.append("total_mismatch")

    if total is None:
        valid: bool | None = None
    else:
        valid = not reasons
    return InvoiceMathCheck(
        line_checks=line_checks,
        expected_total=expected_total,
        actual_total=actual_total,
        total_delta=total_delta,
        valid=valid,
        reasons=reasons,
    )

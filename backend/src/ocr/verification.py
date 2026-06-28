"""Verificación determinista "tipo DNI" de datos de factura (ADR-0010).

Los campos numéricos clave de una factura (NIF/NIE/CIF, IBAN, importes) NO dependen de
que la IA los "lea bien": se verifican con algoritmos deterministas —dígitos de control y
cuadre aritmético—, igual que el lector de un DNI valida su dígito de control. Un valor que
el OCR lea mal y rompa el dígito de control se detecta y se marca para revisión, en lugar de
darse por bueno y llegar a contabilidad como si fuera correcto (regla anti-alucinación).

Este módulo es puro y sin dependencias externas: entra texto, sale un veredicto determinista.
La comprobación online contra VIES/AEAT (que el CIF existe y pertenece a la empresa) vive en
otro módulo porque requiere red; aquí solo está la validación estructural y aritmética.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

__all__ = [
    "CheckResult",
    "TaxLine",
    "validate_nif",
    "validate_nie",
    "validate_cif",
    "validate_tax_id",
    "validate_iban",
    "check_tax_line",
    "check_invoice_totals",
    "DEFAULT_MONEY_TOLERANCE",
]

# --- Tablas y constantes de los algoritmos oficiales ---------------------------------------

# Letra de control del NIF/NIE: índice = número de control módulo 23.
_NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
# Prefijo del NIE convertido a dígito antes de aplicar el algoritmo del NIF.
_NIE_PREFIX = {"X": "0", "Y": "1", "Z": "2"}
# Letra de control del CIF cuando el control es una letra: índice = dígito de control.
_CIF_CONTROL_LETTERS = "JABCDEFGHI"
# Tipos de organización (primera letra del CIF) cuyo control DEBE ser letra.
_CIF_LETTER_ONLY = frozenset("KPQS")
# Tipos cuyo control DEBE ser número.
_CIF_DIGIT_ONLY = frozenset("ABEH")
# Tipos válidos de CIF (el resto admite control numérico o letra).
_CIF_TYPES = frozenset("ABCDEFGHJNPQRSUVW")

# Conjunto de caracteres permitidos al "limpiar" un identificador o IBAN.
_STRIP_CHARS = " -.\t"

# Tolerancia por defecto (en euros) para el cuadre aritmético: absorbe redondeos legales.
DEFAULT_MONEY_TOLERANCE = Decimal("0.02")
# Base de un porcentaje: un tipo de IVA del 21% es 21/100 de la base.
_PERCENT_BASE = Decimal(100)


@dataclass(frozen=True)
class CheckResult:
    """Resultado de una verificación determinista.

    `valid` es el veredicto; `reason` explica el fallo cuando `valid` es False (texto en
    español, pensado para registrarse y, si procede, mostrarse en la pantalla de revisión).
    """

    valid: bool
    reason: str = ""


def _normalize(value: str) -> str:
    """Mayúsculas y sin separadores habituales (espacios, guiones, puntos)."""
    cleaned = value.strip().upper()
    return "".join(ch for ch in cleaned if ch not in _STRIP_CHARS)


# --- Identificadores fiscales españoles ----------------------------------------------------


def validate_nif(value: str) -> CheckResult:
    """NIF de persona física española: 8 dígitos + letra de control (módulo 23)."""
    nif = _normalize(value)
    if len(nif) != 9 or not nif[:8].isdigit() or not nif[8].isalpha():
        return CheckResult(False, "Formato de NIF inválido (esperado: 8 dígitos + letra)")
    expected = _NIF_LETTERS[int(nif[:8]) % 23]
    if nif[8] != expected:
        return CheckResult(False, f"Letra de control de NIF incorrecta (esperada {expected})")
    return CheckResult(True)


def validate_nie(value: str) -> CheckResult:
    """NIE de extranjero: prefijo X/Y/Z + 7 dígitos + letra (mismo algoritmo que el NIF)."""
    nie = _normalize(value)
    if len(nie) != 9 or nie[0] not in _NIE_PREFIX or not nie[1:8].isdigit() or not nie[8].isalpha():
        return CheckResult(False, "Formato de NIE inválido (esperado: X/Y/Z + 7 dígitos + letra)")
    number = int(_NIE_PREFIX[nie[0]] + nie[1:8])
    expected = _NIF_LETTERS[number % 23]
    if nie[8] != expected:
        return CheckResult(False, f"Letra de control de NIE incorrecta (esperada {expected})")
    return CheckResult(True)


def validate_cif(value: str) -> CheckResult:
    """CIF de entidad: letra de tipo + 7 dígitos + dígito/letra de control."""
    cif = _normalize(value)
    if len(cif) != 9 or cif[0] not in _CIF_TYPES or not cif[1:8].isdigit():
        return CheckResult(False, "Formato de CIF inválido (esperado: letra + 7 dígitos + control)")

    total = 0
    for position, digit_char in enumerate(cif[1:8]):
        digit = int(digit_char)
        if position % 2 == 0:  # posiciones impares (1.ª, 3.ª...): se duplican y se suman cifras
            doubled = digit * 2
            total += doubled // 10 + doubled % 10
        else:  # posiciones pares: se suman tal cual
            total += digit
    control_digit = (10 - total % 10) % 10
    control_letter = _CIF_CONTROL_LETTERS[control_digit]

    org_type = cif[0]
    actual = cif[8]
    if org_type in _CIF_LETTER_ONLY:
        ok = actual == control_letter
    elif org_type in _CIF_DIGIT_ONLY:
        ok = actual == str(control_digit)
    else:
        ok = actual in (str(control_digit), control_letter)
    if not ok:
        return CheckResult(False, "Dígito de control de CIF incorrecto")
    return CheckResult(True)


def validate_tax_id(value: str) -> CheckResult:
    """Valida un identificador fiscal español detectando si es NIF, NIE o CIF."""
    normalized = _normalize(value)
    if not normalized:
        return CheckResult(False, "Identificador fiscal vacío")
    first = normalized[0]
    if first.isdigit():
        return validate_nif(normalized)
    if first in _NIE_PREFIX:
        return validate_nie(normalized)
    if first in _CIF_TYPES:
        return validate_cif(normalized)
    return CheckResult(False, "Identificador fiscal no reconocido como NIF, NIE ni CIF")


# --- IBAN ----------------------------------------------------------------------------------


def validate_iban(value: str, *, country: str | None = "ES") -> CheckResult:
    """Valida un IBAN por su checksum ISO 13616 (módulo 97).

    Si se indica `country` (por defecto "ES") se exige además ese prefijo y su longitud.
    """
    iban = _normalize(value)
    if len(iban) < 15 or len(iban) > 34 or not iban[:2].isalpha() or not iban[2:4].isdigit():
        return CheckResult(False, "Formato de IBAN inválido")
    if country is not None:
        if not iban.startswith(country):
            return CheckResult(False, f"El IBAN no es de {country}")
        if country == "ES" and len(iban) != 24:
            return CheckResult(False, "Un IBAN español debe tener 24 caracteres")

    rearranged = iban[4:] + iban[:4]
    digits = []
    for ch in rearranged:
        if ch.isdigit():
            digits.append(ch)
        elif ch.isalpha():
            digits.append(str(ord(ch) - 55))  # A=10 ... Z=35
        else:
            return CheckResult(False, "El IBAN contiene caracteres no permitidos")
    if int("".join(digits)) % 97 != 1:
        return CheckResult(False, "Checksum de IBAN incorrecto")
    return CheckResult(True)


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

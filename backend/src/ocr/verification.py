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


def check_tax_line(
    base: Decimal,
    iva_pct: Decimal,
    cuota: Decimal,
    *,
    tolerance: Decimal = DEFAULT_MONEY_TOLERANCE,
) -> CheckResult:
    """Comprueba que base x IVA% = cuota (con tolerancia de redondeo)."""
    expected = base * iva_pct / Decimal(100)
    if abs(expected - cuota) > tolerance:
        return CheckResult(
            False,
            f"Descuadre de tramo: {base} x {iva_pct}% = {expected}, pero cuota declarada {cuota}",
        )
    return CheckResult(True)


def check_invoice_totals(
    lines: list[tuple[Decimal, Decimal]],
    total: Decimal,
    *,
    irpf_cuota: Decimal = Decimal(0),
    tolerance: Decimal = DEFAULT_MONEY_TOLERANCE,
) -> CheckResult:
    """Comprueba el cuadre global: Σbases + Σcuotas IVA − IRPF = total.

    `lines` es una lista de tramos (base, cuota_iva). `irpf_cuota` es la retención (>= 0).
    """
    sum_base = sum((line[0] for line in lines), Decimal(0))
    sum_iva = sum((line[1] for line in lines), Decimal(0))
    expected = sum_base + sum_iva - irpf_cuota
    if abs(expected - total) > tolerance:
        return CheckResult(
            False,
            f"Descuadre de total: Σbases {sum_base} + ΣIVA {sum_iva} − IRPF {irpf_cuota} "
            f"= {expected}, pero total declarado {total}",
        )
    return CheckResult(True)

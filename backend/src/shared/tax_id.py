"""Validación determinista "tipo DNI" de identificadores fiscales españoles e IBAN.

Primitivo de dominio general (no específico de OCR): entra texto, sale un veredicto determinista
basado en dígitos de control (módulo 23 del NIF/NIE, control del CIF, módulo 97 del IBAN). Lo usan
`companies` (alta/edición de empresas) y, a través de ellos, `identity` (registro con CIF), además
de la capa de verificación OCR (`ocr.verification`), que reutiliza estas piezas sin duplicarlas.

Módulo puro y sin dependencias externas. La comprobación online contra VIES/AEAT (que el CIF existe
y pertenece a la empresa) vive en otra capa porque requiere red; aquí solo está la validación
estructural y aritmética.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CheckResult",
    "validate_nif",
    "validate_nie",
    "validate_cif",
    "validate_tax_id",
    "normalize_tax_id",
    "validate_iban",
]

# --- Tablas y constantes de los algoritmos oficiales ---------------------------------------

# Letra de control del NIF/NIE: índice = número de control módulo 23.
_NIF_LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"
# Prefijo del NIE convertido a dígito antes de aplicar el algoritmo del NIF.
_NIE_PREFIX = {"X": "0", "Y": "1", "Z": "2"}
# Letra de control del CIF cuando el control es una letra: índice = dígito de control.
_CIF_CONTROL_LETTERS = "JABCDEFGHI"
# Tipos de organización (primera letra del CIF) cuyo control DEBE ser letra (P, Q, S).
# Solo estas claves de organismo público han exigido control alfabético de forma estable.
_CIF_LETTER_ONLY = frozenset("PQS")
# Tipos cuyo control DEBE ser número.
_CIF_DIGIT_ONLY = frozenset("ABEH")
# Tipos válidos de CIF (el resto admite control numérico o letra). N (entidades extranjeras),
# W (establecimientos permanentes de no residentes) y R (congregaciones) se dejan a propósito
# en la rama permisiva "número o letra": las fuentes oficiales son contradictorias sobre su
# control (BP-2; ver docs/specs/BP-2-clasificacion-control-cif.md) y la implementación de
# referencia python-stdnum acepta ambos. Exigir letra introduciría falsos rechazos de CIFs
# N/W válidos, y esta capa L1 bloquea "Confirmar y guardar". K no es clave de CIF (es un NIF
# especial de persona física), por eso queda fuera de _CIF_TYPES.
_CIF_TYPES = frozenset("ABCDEFGHJNPQRSUVW")

# Conjunto de caracteres permitidos al "limpiar" un identificador o IBAN.
_STRIP_CHARS = " -.\t"


@dataclass(frozen=True)
class CheckResult:
    """Resultado de una verificación determinista.

    `valid` es el veredicto; `reason` explica el fallo cuando `valid` es False (texto en
    español, pensado para registrarse y, si procede, mostrarse en la pantalla de revisión).
    """

    valid: bool
    reason: str = ""


def _normalize(value: str | None) -> str:
    """Mayúsculas y sin separadores habituales (espacios, guiones, puntos).

    Tolera `None` (campo que el OCR no leyó = `null`, regla anti-alucinación): se trata como
    cadena vacía para que el validador devuelva un veredicto "no válido" tranquilo en vez de
    lanzar `AttributeError`. Punto único de defensa contra el campo no leído (BP-4).
    """
    if value is None:
        return ""
    cleaned = value.strip().upper()
    return "".join(ch for ch in cleaned if ch not in _STRIP_CHARS)


# --- Identificadores fiscales españoles ----------------------------------------------------


def validate_nif(value: str | None) -> CheckResult:
    """NIF de persona física española: 8 dígitos + letra de control (módulo 23)."""
    nif = _normalize(value)
    if len(nif) != 9 or not nif[:8].isdigit() or not nif[8].isalpha():
        return CheckResult(False, "Formato de NIF inválido (esperado: 8 dígitos + letra)")
    expected = _NIF_LETTERS[int(nif[:8]) % 23]
    if nif[8] != expected:
        return CheckResult(False, f"Letra de control de NIF incorrecta (esperada {expected})")
    return CheckResult(True)


def validate_nie(value: str | None) -> CheckResult:
    """NIE de extranjero: prefijo X/Y/Z + 7 dígitos + letra (mismo algoritmo que el NIF)."""
    nie = _normalize(value)
    if len(nie) != 9 or nie[0] not in _NIE_PREFIX or not nie[1:8].isdigit() or not nie[8].isalpha():
        return CheckResult(False, "Formato de NIE inválido (esperado: X/Y/Z + 7 dígitos + letra)")
    number = int(_NIE_PREFIX[nie[0]] + nie[1:8])
    expected = _NIF_LETTERS[number % 23]
    if nie[8] != expected:
        return CheckResult(False, f"Letra de control de NIE incorrecta (esperada {expected})")
    return CheckResult(True)


def validate_cif(value: str | None) -> CheckResult:
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


def normalize_tax_id(value: str | None) -> str:
    """Forma canónica de un identificador fiscal: mayúsculas y sin separadores.

    Punto único de normalización (misma regla que usa la validación): permite que dos escrituras
    del mismo CIF con distinto formato ("a-39.031.620" y "A39031620") colapsen a la misma clave de
    unicidad. `None`/vacío -> cadena vacía.
    """
    return _normalize(value)


def validate_tax_id(value: str | None) -> CheckResult:
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


def validate_iban(value: str | None, *, country: str | None = "ES") -> CheckResult:
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

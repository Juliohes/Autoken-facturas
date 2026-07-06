"""Normalización para comparar el ground truth con el texto de un motor OCR (bench 1.2).

El motor escribe los campos con formatos variados (coma o punto decimal, separadores de fecha,
puntos y espacios en los CIF). Estas funciones permiten un recall tolerante al formato: se compara
por el valor, no por la representación literal.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

# Caracteres de ruido que no cambian la identidad de un CIF/NIF ni de un texto para buscarlo.
_NOISE = re.compile(r"[\s.\-]")


def normalize_text(text: str) -> str:
    """Quita espacios, puntos y guiones y sube a mayúsculas (para buscar CIF dentro del texto)."""
    return _NOISE.sub("", text).upper()


def normalize_tax_id(value: str) -> str:
    """Normaliza un NIF/CIF/NIE: sin espacios/puntos/guiones y en mayúsculas."""
    return normalize_text(value)


def parse_amount(value: str) -> Decimal:
    """Convierte un importe en `Decimal`, entendiendo formato español e inglés.

    Reglas: se elimina todo lo que no sea dígito o separador; si conviven `.` y `,`, el separador
    decimal es el que aparece más a la derecha; con un solo `.` de tres decimales (p. ej. `1.234`)
    se interpreta como separador de miles.
    """
    s = re.sub(r"[^\d.,]", "", value)
    if not s:
        raise ValueError(f"importe no numérico: {value!r}")

    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):  # coma decimal (formato español)
            s = s.replace(".", "").replace(",", ".")
        else:  # punto decimal (formato inglés)
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") == 1:
        entero, decimales = s.split(".")
        if len(decimales) == 3 and len(entero) <= 3:  # 1.234 -> miles, no decimal
            s = entero + decimales
    else:
        s = s.replace(".", "")  # varios puntos = separadores de miles

    return Decimal(s)


def amount_variants(amount: Decimal) -> set[str]:
    """Formas habituales de escribir un importe (coma/punto decimal, con y sin miles)."""
    q = amount.quantize(Decimal("0.01"))
    entero, decimales = f"{q:f}".split(".")
    negativo = entero.startswith("-")
    digitos = entero.lstrip("-")
    agrupado = _group_thousands(digitos)
    signo = "-" if negativo else ""
    return {
        f"{signo}{digitos}.{decimales}",  # 996.40 / 1234.56
        f"{signo}{digitos},{decimales}",  # 996,40 / 1234,56
        f"{signo}{agrupado.replace(',', '.')},{decimales}",  # ES con miles: 1.234,56
        f"{signo}{agrupado}.{decimales}",  # EN con miles: 1,234.56
    }


def _group_thousands(digits: str) -> str:
    """Agrupa de tres en tres con coma: '1234' -> '1,234'."""
    return f"{int(digits):,}"


# Nombres de mes (índice 1..12) que aparecen en factura española/inglesa, forma larga y abreviada.
# Solo se generan los del mes CORRECTO al buscar, así un match laxo nunca casa un mes equivocado.
_MONTH_NAMES: dict[int, tuple[str, ...]] = {
    1: ("enero", "ene", "january", "jan"),
    2: ("febrero", "feb", "february"),
    3: ("marzo", "mar", "march"),
    4: ("abril", "abr", "april", "apr"),
    5: ("mayo", "may", "may"),
    6: ("junio", "jun", "june"),
    7: ("julio", "jul", "july"),
    8: ("agosto", "ago", "august", "aug"),
    9: ("septiembre", "sept", "sep", "september"),
    10: ("octubre", "oct", "october"),
    11: ("noviembre", "nov", "november"),
    12: ("diciembre", "dic", "december", "dec"),
}


def date_matches(text: str, value: date) -> bool:
    """¿Aparece la fecha `value` en `text`, en cualquier formato habitual de factura?

    Reconoce numérico con separador `/ - .` (día/mes con o sin cero delante, año a 4 o 2 cifras),
    ISO `AAAA-MM-DD` y **mes en texto** español/inglés ("18 de mayo de 2026", "May 18, 2026"). Solo
    se construyen patrones para el día/mes/año exactos del ground truth: un match laxo puede tolerar
    ruido de separadores, pero nunca casa una fecha distinta.
    """
    hay = text.lower()
    d, m, y = value.day, value.month, value.year
    sep = r"[/\-.]\s*"
    day = rf"0?{d}"
    year = rf"(?:{y}|{y % 100:02d})"

    # Numérico día-mes-año (ES) e ISO año-mes-día. \b evita casar dentro de un número mayor.
    dmy = rf"\b{day}{sep}0?{m}{sep}{year}\b"
    iso = rf"\b{y}{sep}0?{m}{sep}0?{d}\b"
    if re.search(dmy, hay) or re.search(iso, hay):
        return True

    # Mes en texto: día y año alrededor del nombre del mes (en cualquiera de los dos órdenes).
    for name in _MONTH_NAMES[m]:
        before = rf"\b{day}\b.{{0,6}}{name}.{{0,6}}\b{y}\b"  # 18 de mayo de 2026
        after = rf"{name}\s+{day}\b.{{0,4}}\b{y}\b"  # May 18, 2026
        if re.search(before, hay) or re.search(after, hay):
            return True
    return False

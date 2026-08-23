"""Normalización conservadora de valores OCR para comparar motores (R-035)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from shared.tax_id import normalize_tax_id as _normalize_shared_tax_id

__all__ = [
    "normalize_amount",
    "normalize_date",
    "normalize_invoice_number",
    "normalize_name",
    "normalize_tax_id",
]


def normalize_tax_id(value: Any) -> str | None:
    """Normaliza CIF/NIF sin cambiar su significado."""
    if value is None:
        return None
    normalized = _normalize_shared_tax_id(str(value))
    return normalized or None


def normalize_date(value: Any) -> str | None:
    """Devuelve una fecha válida en formato ISO, o `None` si no es parseable."""
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        return None


def normalize_amount(value: Any) -> str | None:
    """Canonicaliza un importe decimal y rechaza valores no finitos."""
    if value is None:
        return None
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    normalized = amount.normalize()
    return format(normalized, "f")


def normalize_invoice_number(value: Any) -> str | None:
    """Normaliza espacios y mayúsculas sin borrar `/` ni `-`."""
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", str(value).strip()).upper()
    return normalized or None


def normalize_name(value: Any) -> str | None:
    """Normaliza Unicode y espacios para comparar, conservando el original fuera de esta función."""
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(value))
    normalized = re.sub(r"\s+", " ", normalized.strip()).casefold()
    return normalized or None

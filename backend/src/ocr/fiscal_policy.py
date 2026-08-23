"""Política fiscal inicial separada del parser OCR (R-037)."""

from __future__ import annotations

from decimal import Decimal

__all__ = ["is_known_iva_rate"]

_KNOWN_IVA_RATES = frozenset({Decimal("21"), Decimal("10"), Decimal("4"), Decimal("0")})


def is_known_iva_rate(rate: Decimal) -> bool:
    """Indica si el tipo pertenece a la política estándar actual, sin descartar otros tipos."""
    return rate.is_finite() and rate in _KNOWN_IVA_RATES

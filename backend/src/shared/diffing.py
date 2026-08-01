"""`Correction`: un campo cuyo valor cambió entre dos versiones (diff genérico, sin dominio propio).

Extraído de `invoicing.corrections` (2026-08-01) al necesitarlo también `companies` para su propio
historial de ediciones (`company_edits`): vivía en `invoicing` sin ningún acoplamiento real a
facturas, así que mantenerlo ahí habría invertido la dirección de dependencias del proyecto
(`invoicing -> companies`, nunca al revés — `invoicing/service.py` ya importa de `companies`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Correction:
    """Un campo cuyo valor nuevo difiere del anterior (nombres `ai_value`/`human_value`: el uso
    original era OCR-vs-humano; también sirve para humano-vs-humano, como en `company_edits`)."""

    field: str
    ai_value: str | None
    human_value: str | None

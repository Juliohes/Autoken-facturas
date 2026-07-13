"""Constantes de dominio de la verificación del CIF de contraparte (S2.8, ADR-0011).

Fuente ÚNICA de los literales del veredicto del CIF, para que ni el servicio (`counterparty`) ni
sus consumidores (p. ej. `invoicing`, que reimpone el bloqueo al confirmar) los re-hardcodeen.
Es un `StrEnum`: cada miembro es un `str` (intercambiable con el texto que viaja por la API/BD), con
nombre simbólico y conjunto cerrado.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["CifStatus"]


class CifStatus(StrEnum):
    """Estado del veredicto del CIF de contraparte (S2.8).

    `valid` (existe; ver `name_match`), `invalid` (estructura KO o incoherente: bloquea al
    confirmar), `not_found` (una fuente autoritativa afirma que no consta: bloquea), `unverified`
    (ninguna fuente pudo resolver: revisar manual, NO bloquea).
    """

    VALID = "valid"
    INVALID = "invalid"
    NOT_FOUND = "not_found"
    UNVERIFIED = "unverified"

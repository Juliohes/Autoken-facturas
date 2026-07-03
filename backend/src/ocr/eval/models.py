"""Modelo del ground truth de una factura para el bench OCR (1.2).

Registra TODOS los identificadores fiscales del documento (no solo la contraparte), la fecha y los
importes, para medir la calidad de LECTURA de cada motor con independencia de qué tenant la suba.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class Party(BaseModel):
    """Una parte de la factura: emisor (`issuer`) o receptor (`recipient`)."""

    role: Literal["issuer", "recipient"]
    name: str | None = None
    tax_id: str | None = None


class GroundTruth(BaseModel):
    """Verdad de referencia de una factura. Lo transcribe Claude; Julio valida una muestra."""

    invoice_id: str
    source_file: str
    parties: tuple[Party, ...] = ()
    issue_date: date | None = None
    total_amount: Decimal | None = None
    net_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    # Identificador que se considerará contraparte respecto al tenant (para la capa S2.8, no para
    # el scorer de lectura). Se rellena cuando se decide el tenant de cada factura del dataset.
    counterparty_tax_id: str | None = None
    # Confianza de la transcripción y notas (documento borroso, girado, no es factura, etc.). Guían
    # la validación de Julio; no intervienen en el scoring.
    read_confidence: Literal["alta", "media", "baja"] | None = None
    notes: str | None = None
    validated_by_julio: bool = False

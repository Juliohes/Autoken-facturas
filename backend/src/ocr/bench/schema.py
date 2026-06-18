"""Modelo de datos del bench de motores OCR (tarea 1.2).

Define el contrato común que todos los motores —cloud y self-hosted— deben rellenar para
poder compararse de forma justa: los mismos campos de factura, una confianza por campo, y el
coste y la latencia reales de la extracción. Es un modelo puro (sin dependencias externas)
para que el bench se ejecute en CI sin tocar ningún servicio de pago.

Los campos canónicos son los que el PLAN MAESTRO (§4, tarea 1.2) exige medir: número de
factura, identificadores fiscales y nombres de emisor y receptor, fecha, tramos de IVA,
retención de IRPF y total. La comparación contra el ground truth y la verificación
determinista "tipo DNI" (ADR-0010) operan sobre este modelo.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

# --- Campos canónicos -----------------------------------------------------------------------

# Campos escalares que se puntúan uno a uno contra el ground truth. `tramos` se trata aparte
# porque es una lista y se compara como multiconjunto (ver scoring.py).
SCALAR_FIELDS: tuple[str, ...] = (
    "numero",
    "fecha",
    "emisor_nombre",
    "emisor_nif",
    "receptor_nombre",
    "receptor_nif",
    "irpf_cuota",
    "total",
)

# Todos los campos puntuables, en el orden en que aparecen en el informe.
SCORABLE_FIELDS: tuple[str, ...] = (*SCALAR_FIELDS, "tramos")

# Agrupación para la tabla resumen del informe (las "categorías" del plan).
FIELD_GROUPS: Mapping[str, tuple[str, ...]] = {
    "nº factura": ("numero",),
    "fecha": ("fecha",),
    "CIFs": ("emisor_nif", "receptor_nif"),
    "nombres": ("emisor_nombre", "receptor_nombre"),
    "tramos IVA": ("tramos",),
    "IRPF": ("irpf_cuota",),
    "total": ("total",),
}


@dataclass(frozen=True)
class TaxLine:
    """Un tramo de IVA: base imponible, tipo (%) y cuota resultante."""

    base: Decimal
    iva_pct: Decimal
    cuota: Decimal


@dataclass(frozen=True)
class InvoiceFields:
    """Campos estructurados de una factura, tal como los lee un motor o los fija el ground truth.

    Todo campo es opcional: un motor que no lee un dato con certeza debe dejarlo en `None`
    (regla anti-alucinación, §1 del plan), NUNCA inventarlo. Un `None` frente a un valor real
    en el ground truth cuenta como fallo de cobertura; un valor inventado, como fallo de
    precisión. Ambos se distinguen en el scoring.
    """

    numero: str | None = None
    fecha: str | None = None  # ISO 8601 (AAAA-MM-DD)
    emisor_nombre: str | None = None
    emisor_nif: str | None = None
    receptor_nombre: str | None = None
    receptor_nif: str | None = None
    tramos: tuple[TaxLine, ...] = ()
    irpf_cuota: Decimal | None = None
    total: Decimal | None = None


@dataclass(frozen=True)
class EngineResult:
    """Salida de un motor para una factura, con su coste y latencia reales.

    `confidences` mapea nombre de campo → confianza [0, 1]; los motores que no la reporten
    pueden omitir campos (el enrutado por confianza del plan los tratará como confianza 0).
    `raw` guarda el JSON crudo del motor para auditoría y depuración del prompt.
    """

    engine: str
    fields: InvoiceFields
    confidences: Mapping[str, float] = field(default_factory=dict)
    duration_ms: int = 0
    cost_eur: Decimal = Decimal(0)
    raw: Mapping[str, object] = field(default_factory=dict)
    error: str | None = None

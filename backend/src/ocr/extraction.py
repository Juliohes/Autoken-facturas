"""Contrato de extracción de campos de una factura (S2.3, ADR-0016).

Módulo PURO del dominio de extracción: solo la abstracción (`InvoiceExtractor`, un `Protocol`), los
tipos de dominio (`ExtractedInvoice`, `ExtractedTaxId`, `ExtractedTaxLine`, `Confidence`) y el error
de proveedor (`InvoiceExtractionError`). Aquí NO vive ningún motor real ni infraestructura de red,
para que los módulos puros que dependen del contrato (`ocr.arbiter`, `ocr.analysis`) no arrastren
el SDK. El adaptador real (gemini-3-flash a JSON) vive en `ocr.engines.gemini_extractor`.

Regla anti-alucinación: un campo no legible se representa con `None` (nunca un valor inventado) y su
confianza baja; el enrutado por confianza (`is_low`) decide qué va a revisión.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Protocol, cast, runtime_checkable

__all__ = [
    "Confidence",
    "CONFIDENCE_VALUES",
    "CONFIDENCE_RANK",
    "is_low",
    "ExtractedTaxId",
    "ExtractedTaxLine",
    "ExtractedInvoice",
    "DocumentPage",
    "InvoiceExtractor",
    "InvoiceExtractionError",
    "extract_document",
    "serialize_tax_lines",
]

# Confianza por campo (enrutado): `alta` = fiable; `media` = dudoso; `baja` = no fiable (revisar).
Confidence = Literal["alta", "media", "baja"]

# Fuente ÚNICA del vocabulario de confianza y su orden. Lo comparten el árbitro (elegir la mejor
# lectura), el análisis (enrutado por confianza) y el adaptador real (normalizar la etiqueta del
# proveedor): no se duplica en cada módulo.
CONFIDENCE_VALUES: frozenset[str] = frozenset({"alta", "media", "baja"})
# Orden de menor a mayor fiabilidad (mayor gana al reconciliar por campo).
CONFIDENCE_RANK: dict[Confidence, int] = {"baja": 0, "media": 1, "alta": 2}


def is_low(confidence: Confidence) -> bool:
    """True si la confianza NO es `alta` (dudosa o no fiable): enruta a revisión reforzada."""
    return confidence != "alta"


@dataclass(frozen=True)
class ExtractedTaxId:
    """Un identificador fiscal leído en la factura: valor, razón social y confianza de lectura.

    `value` a `None` es un identificador no legible (regla anti-alucinación): se marca, no se crea.
    """

    value: str | None
    name: str | None
    confidence: Confidence


@dataclass(frozen=True)
class ExtractedTaxLine:
    """Un tramo de impuesto leído: base imponible, tipo (%) y cuota."""

    base: Decimal
    rate: Decimal
    cuota: Decimal


@dataclass(frozen=True)
class ExtractedInvoice:
    """Campos de oro de una factura leídos por el extractor, con su confianza por campo.

    El foco de lectura es fecha + importes + identificadores fiscales + número de factura; el
    CIF/nombre propios NO se leen aquí (se conocen desde `companies` y se inyectan en el análisis).
    `net_amount`/`tax_amount` llevan confianza propia desde S6.1 (antes salían sin puntuar). `raw`
    deja la respuesta del proveedor para trazabilidad, sin acoplar el dominio a su formato.
    """

    issue_date: date | None
    issue_date_confidence: Confidence
    total_amount: Decimal | None
    total_confidence: Confidence
    net_amount: Decimal | None
    net_amount_confidence: Confidence
    tax_amount: Decimal | None
    tax_amount_confidence: Confidence
    invoice_number: str | None
    invoice_number_confidence: Confidence
    tax_lines: tuple[ExtractedTaxLine, ...]
    tax_ids: tuple[ExtractedTaxId, ...]
    engine: str
    model: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class DocumentPage:
    """Una hoja ya descargada del documento, conservando inequívocamente su orden."""

    content: bytes
    content_type: str


def serialize_tax_lines(invoice: ExtractedInvoice) -> list[dict[str, str]]:
    """Tramos a JSON-friendly: los importes como `str` para no perder precisión decimal en jsonb.

    Compartida entre `jobs.ocr` (persistencia de `ocr_extractions`) y `ocr.comparison`
    (persistencia de `ocr_comparison_runs`, S2.10): mismo criterio de serialización en un único
    sitio, para que no puedan divergir en silencio (auditoría, hallazgo de duplicación).
    """
    return [
        {"base": str(line.base), "rate": str(line.rate), "cuota": str(line.cuota)}
        for line in invoice.tax_lines
    ]


class InvoiceExtractionError(Exception):
    """Fallo del proveedor de extracción (credenciales, red, timeout o respuesta ilegible).

    Frontera del proveedor: el job la trata como "el motor falló" (-> `ocr_failed`), sin persistir
    una extracción parcial mentirosa.
    """


@runtime_checkable
class InvoiceExtractor(Protocol):
    """Extractor de factura: dada la imagen/PDF, devuelve un `ExtractedInvoice` con confianzas."""

    async def extract(self, content: bytes, content_type: str) -> ExtractedInvoice:
        """Lee el documento y devuelve los campos de oro; `InvoiceExtractionError` al fallar."""
        ...


async def extract_document(
    extractor: InvoiceExtractor, pages: list[DocumentPage]
) -> ExtractedInvoice:
    """Llama al contrato multipágina o falla de forma explícita, nunca degrada a página 1.

    Mantiene la compatibilidad de los dobles históricos para documentos simples. Para dos o más
    páginas un extractor antiguo sin `extract_pages` es un error del proveedor, no una omisión.
    """
    if not pages:
        raise InvoiceExtractionError("El documento no contiene páginas")
    extract_pages = getattr(extractor, "extract_pages", None)
    if callable(extract_pages):
        return cast(ExtractedInvoice, await extract_pages(pages))
    if len(pages) == 1:
        return await extractor.extract(pages[0].content, pages[0].content_type)
    raise InvoiceExtractionError("El extractor no admite documentos multipágina")

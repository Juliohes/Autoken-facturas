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
    "extracted_invoice_from_record",
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
    """Un identificador fiscal leído en la factura: valor, razón social y su confianza de lectura.

    `value` a `None` es un identificador no legible (regla anti-alucinación): se marca, no se crea.

    S6.14: la confianza del VALOR (CIF/NIF) y la del NOMBRE asociado se conocen por separado
    (`value_confidence`/`name_confidence`), en vez de una única confianza combinada. Motivo (dato
    empírico del bench S6.7, 29 facturas reales): el CIF acierta el 89,66% de las veces y el nombre
    solo el 58,62% — una sola confianza combinada no permite decir "seguro del CIF, dudoso del
    nombre", y el nombre comercial de un logo puede no coincidir con la razón social legal junto al
    CIF sin que el motor lo señale. El enrutado a revisión (`ocr.analysis`) exige confianza alta en
    el CIF (impacto fiscal real) pero acepta media en el nombre (corrección visual barata, sin
    validación externa).
    """

    value: str | None
    name: str | None
    value_confidence: Confidence
    name_confidence: Confidence


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


def extracted_invoice_from_record(
    record: Any,  # `ocr.repository.ExtractionRecord`; Any para no importar infra (módulo puro)
    *,
    own_cif: str,
) -> ExtractedInvoice:
    """Reconstruye un `ExtractedInvoice` desde la extracción YA persistida (S6.15 C1).

    La comparativa S2.10, al correr como tarea de fondo separada (en vez de inline en `run_ocr`),
    ya no tiene en memoria la lectura original del motor. Para no pagarla de nuevo (hallazgo de
    coste corregido dos veces en el proyecto: nunca se re-lee al motor por defecto si la lectura ya
    existe), la reconstruimos desde la fila de `ocr_extractions` — que ES esa lectura, persistida.

    Fidelidad del análisis posterior (`analyze_invoice`): se incluye la contraparte (desde las
    columnas cifradas descifradas) y, si `own_tax_id_present` es True, también el CIF propio (con
    confianza alta, pues el análisis original ya confirmó su presencia). Así el análisis que haga la
    comparativa sobre esta lectura reproduce el `own_tax_id_present` persistido, sin sesgarla.

    Las confianzas por campo se leen del dict persistido (`record.confidences`, claves de
    `ocr.analysis`: `issue_date`, `total_amount`, ...); las ausentes caen a "baja" (regla
    anti-alucinación, nunca una confianza inventada).
    """
    confidences: dict[str, Any] = record.confidences or {}

    def _conf(key: str) -> Confidence:
        value = confidences.get(key)
        return value if value in CONFIDENCE_VALUES else "baja"

    tax_ids: list[ExtractedTaxId] = []
    if record.counterparty_tax_id is not None or record.counterparty_name is not None:
        tax_ids.append(
            ExtractedTaxId(
                value=record.counterparty_tax_id,
                name=record.counterparty_name,
                value_confidence=_conf("counterparty_tax_id"),
                name_confidence=_conf("counterparty_name"),
            )
        )
    if record.own_tax_id_present and own_cif:
        tax_ids.append(
            ExtractedTaxId(
                value=own_cif, name=None, value_confidence="alta", name_confidence="alta"
            )
        )

    return ExtractedInvoice(
        issue_date=record.issue_date,
        issue_date_confidence=_conf("issue_date"),
        total_amount=record.total_amount,
        total_confidence=_conf("total_amount"),
        net_amount=record.net_amount,
        net_amount_confidence=_conf("net_amount"),
        tax_amount=record.tax_amount,
        tax_amount_confidence=_conf("tax_amount"),
        invoice_number=record.invoice_number,
        invoice_number_confidence=_conf("invoice_number"),
        tax_lines=tuple(
            ExtractedTaxLine(
                base=Decimal(str(line["base"])),
                rate=Decimal(str(line["rate"])),
                cuota=Decimal(str(line["cuota"])),
            )
            for line in (record.tax_lines or [])
        ),
        tax_ids=tuple(tax_ids),
        engine=record.engine,
        model=record.model,
        raw=record.raw,
    )


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

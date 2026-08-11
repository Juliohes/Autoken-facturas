"""Adaptador de Azure Document Intelligence al ranking multi-modelo (S4.8), vía `prebuilt-invoice`.

A diferencia de Gemini/Claude/gpt-5.1 (modelos de lenguaje "promptables"), Azure Document
Intelligence NO es un modelo de lenguaje: no se le puede pedir un esquema de JSON. El motor del
bench (`ocr/engines/azure_docintel.py`) usa `prebuilt-layout` (markdown, sin campos) porque ahí
interesa comparar texto libre. Para el ranking de campos estructurados, este extractor usa en su
lugar el modelo dedicado de Azure para facturas, **`prebuilt-invoice`**, que SÍ devuelve campos
propios (`VendorTaxId`, `CustomerTaxId`, `InvoiceDate`, `InvoiceTotal`...) con su propia confianza —
y este módulo traduce ("mapea") ese esquema al de `ExtractedInvoice`, en vez de parsear JSON de un
prompt.

Nota de incertidumbre (documentada a propósito, no escondida): los nombres de campo de
`prebuilt-invoice` están tomados de la documentación pública de Azure (estables desde su
disponibilidad general) pero no se han podido verificar contra una respuesta real del servicio en
este entorno (harían falta credenciales y una llamada de pago) — la prueba de este extractor usa un
doble con esa forma esperada. `Items` (líneas de producto) no tiene un tramo de IVA por tipo
comparable al dominio español, así que `tax_lines` queda siempre vacío para este motor (honesto: no
inventa un desglose de IVA que Azure no da en ese formato).

No se ejerce en CI: los tests inyectan un doble del cliente. Cualquier fallo del SDK o del mapeo se
traduce a `InvoiceExtractionError`; nunca cruza una excepción cruda.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from ocr.extraction import (
    Confidence,
    ExtractedInvoice,
    ExtractedTaxId,
    InvoiceExtractionError,
    InvoiceExtractor,
)

__all__ = ["ENGINE_NAME", "AzureDocIntelInvoiceExtractor", "build_azure_docintel_extractor"]

ENGINE_NAME = "azure-docintel"
_INVOICE_MODEL = "prebuilt-invoice"

_SUPPORTED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "application/pdf"})

# Umbrales de confianza de Azure (float 0.0-1.0) a la escala del dominio. Sin un veredicto oficial
# de Azure sobre dónde cae "alta"/"media": criterio conservador propio, documentado aquí para poder
# ajustarlo si el ranking real (una vez activado) muestra que hace falta.
_HIGH_CONFIDENCE = 0.9
_MEDIUM_CONFIDENCE = 0.5


class AzureDocIntelInvoiceExtractor:
    """Extractor real basado en Azure Document Intelligence (`prebuilt-invoice`)."""

    def __init__(
        self,
        endpoint: str | None,
        key: str | None,
        *,
        model: str = _INVOICE_MODEL,
        client: Any | None = None,
    ) -> None:
        """Crea el extractor. `client` permite inyectar un doble en test (no se llama a la red)."""
        if client is None and (not endpoint or not key):
            raise InvoiceExtractionError(
                "Faltan las credenciales de Azure DocIntel "
                "(AZURE_DOCINTEL_ENDPOINT / AZURE_DOCINTEL_KEY)"
            )
        self._endpoint = endpoint
        self._key = key
        self._model = model
        self._client = client

    async def extract(self, content: bytes, content_type: str) -> ExtractedInvoice:
        """Manda el documento a `prebuilt-invoice` y mapea sus campos a `ExtractedInvoice`."""
        if content_type not in _SUPPORTED_CONTENT_TYPES:
            raise InvoiceExtractionError(
                f"Tipo de contenido no soportado por el motor: {content_type}"
            )

        try:
            if self._client is not None:  # cliente inyectado en test
                result = await self._analyze(self._client, content)
            else:
                async with self._make_client() as client:
                    result = await self._analyze(client, content)
            return self._map(result)
        except Exception as exc:  # frontera del proveedor: nada crudo cruza al llamador
            raise InvoiceExtractionError(
                f"Azure DocIntel falló al extraer la factura: {exc}"
            ) from exc

    def _make_client(self) -> Any:
        from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        return DocumentIntelligenceClient(
            endpoint=self._endpoint or "", credential=AzureKeyCredential(self._key or "")
        )

    async def _analyze(self, client: Any, content: bytes) -> Any:
        from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

        poller = await client.begin_analyze_document(
            self._model, AnalyzeDocumentRequest(bytes_source=content)
        )
        return await poller.result()

    def _map(self, result: Any) -> ExtractedInvoice:
        """`AnalyzeResult.documents[0].fields` (esquema propio de Azure) -> `ExtractedInvoice`."""
        documents = getattr(result, "documents", None) or []
        fields: dict[str, Any] = documents[0].fields if documents and documents[0].fields else {}
        model_version = getattr(result, "model_id", None) or self._model

        tax_ids = tuple(
            tid
            for tid in (
                self._tax_id(fields, tax_id_field="VendorTaxId", name_field="VendorName"),
                self._tax_id(fields, tax_id_field="CustomerTaxId", name_field="CustomerName"),
            )
            if tid is not None
        )

        return ExtractedInvoice(
            issue_date=self._date_value(fields.get("InvoiceDate")),
            issue_date_confidence=self._confidence(fields.get("InvoiceDate")),
            total_amount=self._currency_value(fields.get("InvoiceTotal")),
            total_confidence=self._confidence(fields.get("InvoiceTotal")),
            net_amount=self._currency_value(fields.get("SubTotal")),
            net_amount_confidence=self._confidence(fields.get("SubTotal")),
            tax_amount=self._currency_value(fields.get("TotalTax")),
            tax_amount_confidence=self._confidence(fields.get("TotalTax")),
            # `InvoiceId`: campo nativo de `prebuilt-invoice` para el número de factura (S6.1).
            invoice_number=self._string_value(fields.get("InvoiceId")),
            invoice_number_confidence=self._confidence(fields.get("InvoiceId")),
            tax_lines=(),  # `Items` de Azure no es un desglose de IVA por tipo (ver docstring).
            tax_ids=tax_ids,
            engine=ENGINE_NAME,
            model=model_version,
            raw={"model_id": model_version},
        )

    def _tax_id(
        self, fields: dict[str, Any], *, tax_id_field: str, name_field: str
    ) -> ExtractedTaxId | None:
        field = fields.get(tax_id_field)
        value = self._string_value(field)
        if value is None:
            return None
        name = self._string_value(fields.get(name_field))
        return ExtractedTaxId(value=value, name=name, confidence=self._confidence(field))

    @staticmethod
    def _string_value(field: Any) -> str | None:
        if field is None:
            return None
        value = getattr(field, "value_string", None) or getattr(field, "content", None)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _date_value(field: Any) -> date | None:
        if field is None:
            return None
        value = getattr(field, "value_date", None)
        if value is None:
            return None
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    @staticmethod
    def _currency_value(field: Any) -> Decimal | None:
        if field is None:
            return None
        currency = getattr(field, "value_currency", None)
        amount = getattr(currency, "amount", None) if currency is not None else None
        if amount is None:
            return None
        return Decimal(str(amount))

    @staticmethod
    def _confidence(field: Any) -> Confidence:
        score = getattr(field, "confidence", None) if field is not None else None
        if score is None:
            return "baja"
        if score >= _HIGH_CONFIDENCE:
            return "alta"
        if score >= _MEDIUM_CONFIDENCE:
            return "media"
        return "baja"


def build_azure_docintel_extractor(settings: Any) -> InvoiceExtractor:
    """Extractor candidato del ranking (S4.8): Azure Document Intelligence, `prebuilt-invoice`."""
    return AzureDocIntelInvoiceExtractor(
        settings.azure_docintel_endpoint, settings.azure_docintel_key
    )

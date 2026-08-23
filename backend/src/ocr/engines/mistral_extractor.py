"""Adaptador de Mistral OCR 4 con anotación JSON estructurada (R-029)."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

from ocr.extraction import ExtractedInvoice, InvoiceExtractionError, InvoiceExtractor
from ocr.extraction_json import parse_structured_invoice
from ocr.schema import INVOICE_EXTRACTION_PROMPT, InvoiceExtractionSchema

__all__ = ["ENGINE_NAME", "MistralInvoiceExtractor", "build_mistral_extractor"]

ENGINE_NAME = "mistral-ocr-4"
_DEFAULT_TIMEOUT_S = 60

_PDF_CONTENT_TYPE = "application/pdf"
_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_SUPPORTED_CONTENT_TYPES: frozenset[str] = _IMAGE_CONTENT_TYPES | {_PDF_CONTENT_TYPE}
_IMAGE_MIME_BY_CONTENT_TYPE = {
    "image/jpeg": "image/jpeg",
    "image/png": "image/png",
    "image/webp": "image/webp",
}


class MistralInvoiceExtractor:
    """Llama a Mistral OCR 4 y convierte su anotación al contrato OCR interno."""

    def __init__(
        self,
        api_key: str | None,
        *,
        model: str,
        timeout_s: int = _DEFAULT_TIMEOUT_S,
        client: Any | None = None,
    ) -> None:
        """Crea el extractor. `client` permite inyectar un doble en test (no se llama a la red)."""
        if client is None and not api_key:
            raise InvoiceExtractionError("Falta la API key de Mistral (MISTRAL_API_KEY)")
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s
        self._client = client

    async def extract(self, content: bytes, content_type: str) -> ExtractedInvoice:
        """Llama a Mistral OCR 4 y valida la anotación estructurada devuelta por el proveedor."""
        if content_type not in _SUPPORTED_CONTENT_TYPES:
            raise InvoiceExtractionError(
                f"Tipo de contenido no soportado por el motor: {content_type}"
            )

        document = self._build_document(content, content_type)
        try:
            client = self._ensure_client()
            response = await client.ocr.process_async(
                model=self._model,
                document=document,
                include_image_base64=False,
                include_blocks=True,
                confidence_scores_granularity="page",
                document_annotation_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "invoice_extraction",
                        "schema": InvoiceExtractionSchema.model_json_schema(),
                    },
                },
                document_annotation_prompt=INVOICE_EXTRACTION_PROMPT,
                timeout_ms=self._timeout_s * 1000,
            )
        except Exception as exc:  # frontera del proveedor: nada crudo cruza al llamador
            raise InvoiceExtractionError(
                f"Mistral OCR falló al procesar la factura: {exc}"
            ) from exc

        model_version = getattr(response, "model", None) or self._model
        raw = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        annotation = getattr(response, "document_annotation", None)
        if not isinstance(annotation, str) or not annotation.strip():
            raise InvoiceExtractionError("Mistral no devolvió document_annotation estructurado")
        try:
            schema = InvoiceExtractionSchema.model_validate(json.loads(annotation))
            invoice = parse_structured_invoice(
                json.dumps(_to_parser_payload(schema)),
                engine=ENGINE_NAME,
                model=model_version,
            )
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise InvoiceExtractionError(
                f"La anotación estructurada de Mistral no es válida: {exc}"
            ) from exc
        return replace(invoice, raw=raw)

    def _build_document(self, content: bytes, content_type: str) -> dict[str, str]:
        import base64

        encoded = base64.b64encode(content).decode("ascii")
        if content_type == _PDF_CONTENT_TYPE:
            return {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{encoded}",
            }
        mime = _IMAGE_MIME_BY_CONTENT_TYPE[content_type]
        return {"type": "image_url", "image_url": f"data:{mime};base64,{encoded}"}

    def _ensure_client(self) -> Any:
        if self._client is None:
            from mistralai.client import Mistral

            self._client = Mistral(api_key=self._api_key or "")
        return self._client


def _to_parser_payload(schema: InvoiceExtractionSchema) -> dict[str, Any]:
    """Traduce el contrato común a las claves históricas del dominio OCR."""
    return {
        "issue_date": schema.issue_date,
        "issue_date_confidence": "baja",
        "total_amount": schema.total_amount,
        "total_confidence": "baja",
        "net_amount": schema.net_amount,
        "net_amount_confidence": "baja",
        "tax_amount": schema.tax_amount,
        "tax_amount_confidence": "baja",
        "irpf_rate": schema.irpf_rate,
        "irpf_rate_confidence": "baja",
        "irpf_amount": schema.irpf_amount,
        "irpf_amount_confidence": "baja",
        "invoice_number": schema.invoice_number,
        "invoice_number_confidence": "baja",
        "tax_lines": [
            {"base": line.base, "rate": line.rate, "cuota": line.quota}
            for line in schema.tax_lines
        ],
        "tax_ids": [
            {
                "value": tax_id.value,
                "name": tax_id.name,
                "value_confidence": "baja",
                "name_confidence": "baja",
            }
            for tax_id in schema.tax_ids
        ],
    }


def build_mistral_extractor(settings: Any) -> InvoiceExtractor:
    """Extractor candidato del ranking (S4.8): Mistral OCR 4, sin campos estructurados (ver §)."""
    return MistralInvoiceExtractor(
        settings.mistral_api_key,
        model=settings.mistral_ocr_model,
        timeout_s=settings.mistral_ocr_timeout,
    )

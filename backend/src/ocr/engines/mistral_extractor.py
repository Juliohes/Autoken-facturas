"""Adaptador de Mistral OCR 4 al ranking multi-modelo (S4.8), sin campos inventados.

Mistral OCR 4 (`POST /v1/ocr`, ver `ocr/engines/mistral_ocr4.py`) es una API de OCR puro: no es un
modelo de lenguaje, no sigue instrucciones, no se le puede "pedir" un esquema de JSON — solo
devuelve markdown y bloques de texto por página. No hay forma honesta de convertir eso en
fecha/importes/CIF verificados sin inventar ese paso intermedio (que además mediría la calidad de
OTRO componente, no la de Mistral).

Decisión de dominio (spec S4.8 §0/C5): este extractor SÍ llama a Mistral (para medir su coste,
latencia y disponibilidad como los demás motores del ranking), pero su lectura estructurada tiene
TODOS los campos a `None` con confianza `baja` — nunca un valor inventado. Es información real: el
ranking de "acierto de campos estructurados" mostrará a Mistral en el fondo por diseño de su propia
API, no por un fallo de este adaptador.

No se ejerce en CI: los tests inyectan un doble del cliente. Cualquier fallo de la API se traduce a
`InvoiceExtractionError`; nunca cruza una excepción cruda.
"""

from __future__ import annotations

from typing import Any

from ocr.extraction import ExtractedInvoice, InvoiceExtractionError, InvoiceExtractor

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
    """Llama a Mistral OCR 4 pero nunca inventa campos: ver docstring del módulo."""

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
        """Llama a Mistral OCR 4; devuelve SIEMPRE una lectura sin campos (ver docstring)."""
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
                timeout_ms=self._timeout_s * 1000,
            )
        except Exception as exc:  # frontera del proveedor: nada crudo cruza al llamador
            raise InvoiceExtractionError(
                f"Mistral OCR falló al procesar la factura: {exc}"
            ) from exc

        model_version = getattr(response, "model", None) or self._model
        raw = response.model_dump() if hasattr(response, "model_dump") else dict(response)
        return _empty_invoice(model=model_version, raw=raw)

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


def _empty_invoice(*, model: str, raw: dict[str, Any]) -> ExtractedInvoice:
    """Lectura sin ningún campo: Mistral no expone extracción estructurada (spec S4.8 §0/C5)."""
    return ExtractedInvoice(
        issue_date=None,
        issue_date_confidence="baja",
        total_amount=None,
        total_confidence="baja",
        net_amount=None,
        net_amount_confidence="baja",
        tax_amount=None,
        tax_amount_confidence="baja",
        irpf_rate=None,
        irpf_rate_confidence="baja",
        irpf_amount=None,
        irpf_amount_confidence="baja",
        invoice_number=None,
        invoice_number_confidence="baja",
        tax_lines=(),
        tax_ids=(),
        engine=ENGINE_NAME,
        model=model,
        raw=raw,
    )


def build_mistral_extractor(settings: Any) -> InvoiceExtractor:
    """Extractor candidato del ranking (S4.8): Mistral OCR 4, sin campos estructurados (ver §)."""
    return MistralInvoiceExtractor(
        settings.mistral_api_key,
        model=settings.mistral_ocr_model,
        timeout_s=settings.mistral_ocr_timeout,
    )

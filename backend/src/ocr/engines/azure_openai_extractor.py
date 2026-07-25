"""Adaptador de extracción a JSON estructurado con Azure OpenAI (gpt-5.1) (S4.8, ranking).

Implementa `ocr.extraction.InvoiceExtractor` con el mismo prompt/parseo compartidos que Gemini
(`ocr.extraction_json`), reutilizando la conexión REST de `ocr/engines/azure_openai.py` (motor del
bench): URL del despliegue, cabecera `api-key`, mismos parámetros de razonamiento de gpt-5.1
(`max_completion_tokens`/`reasoning_effort`, ver notas de despliegue en el motor del bench).

gpt-visión no acepta PDF nativo: se rasteriza antes con `ocr.preprocess.rasterize_pdf` (generalizada
en S4.8 para aceptar bytes en memoria). Con varias páginas, TODAS se adjuntan como imágenes de UN
único mensaje/petición (no una petición por página): es el propio modelo el que razona sobre el
conjunto y devuelve un solo JSON, igual que ya hace Gemini con multi-imagen en el mismo prompt.

No se ejerce en CI: los tests inyectan un doble del cliente HTTP. Cualquier fallo de la API o del
parseo se traduce a `InvoiceExtractionError`; nunca cruza una excepción cruda.
"""

from __future__ import annotations

import base64
from typing import Any

from ocr.extraction import ExtractedInvoice, InvoiceExtractionError, InvoiceExtractor
from ocr.extraction_json import EXTRACTION_PROMPT, parse_structured_invoice
from ocr.preprocess import RasterizeError, rasterize_pdf

__all__ = ["AzureOpenAIInvoiceExtractor", "build_azure_openai_extractor"]

_ENGINE_NAME = "gpt-5.1"
_DEFAULT_TIMEOUT_S = 90.0
_MAX_OUTPUT_TOKENS = 16000
_REASONING_EFFORT = "low"

_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_SUPPORTED_CONTENT_TYPES: frozenset[str] = _IMAGE_CONTENT_TYPES | {"application/pdf"}


class AzureOpenAIInvoiceExtractor:
    """Extractor real basado en gpt-5.1 (Azure OpenAI), prompteado a JSON estructurado."""

    def __init__(
        self,
        endpoint: str | None,
        key: str | None,
        deployment: str | None,
        *,
        api_version: str,
        prompt: str = EXTRACTION_PROMPT,
        timeout_s: float = _DEFAULT_TIMEOUT_S,
        client: Any | None = None,
    ) -> None:
        """Crea el extractor. `client` (httpx.AsyncClient o doble) permite testear sin red."""
        if client is None and (not endpoint or not key or not deployment):
            raise InvoiceExtractionError(
                "Azure OpenAI sin configurar: faltan "
                "AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY / AZURE_OPENAI_DEPLOYMENT en el .env"
            )
        self._endpoint = endpoint
        self._key = key
        self._deployment = deployment
        self._api_version = api_version
        self._prompt = prompt
        self._timeout_s = timeout_s
        self._client = client

    async def extract(self, content: bytes, content_type: str) -> ExtractedInvoice:
        """Manda la factura a gpt-visión pidiendo JSON y lo normaliza a `ExtractedInvoice`."""
        if content_type not in _SUPPORTED_CONTENT_TYPES:
            raise InvoiceExtractionError(
                f"Tipo de contenido no soportado por el motor: {content_type}"
            )

        images = self._image_data_uris(content, content_type)
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._prompt},
                        *(
                            {"type": "image_url", "image_url": {"url": uri, "detail": "high"}}
                            for uri in images
                        ),
                    ],
                }
            ],
            "max_completion_tokens": _MAX_OUTPUT_TOKENS,
            "reasoning_effort": _REASONING_EFFORT,
        }
        headers = {"api-key": self._key or "", "Content-Type": "application/json"}
        url = self._chat_completions_url()

        try:
            import httpx

            if self._client is not None:  # cliente inyectado en test
                response = await self._client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        except Exception as exc:  # frontera del proveedor: nada crudo cruza al llamador
            raise InvoiceExtractionError(
                f"Azure OpenAI falló al extraer la factura: {exc}"
            ) from exc

        choices = body.get("choices") or []
        text = (choices[0].get("message") or {}).get("content") if choices else None
        model_version = body.get("model") or self._deployment or _ENGINE_NAME
        return parse_structured_invoice(text, engine=_ENGINE_NAME, model=model_version)

    def _chat_completions_url(self) -> str:
        base = (self._endpoint or "").rstrip("/")
        return (
            f"{base}/openai/deployments/{self._deployment}"
            f"/chat/completions?api-version={self._api_version}"
        )

    def _image_data_uris(self, content: bytes, content_type: str) -> list[str]:
        """Data URIs a mandar: la imagen tal cual, o cada página del PDF ya rasterizada."""
        if content_type == "application/pdf":
            try:
                pages = rasterize_pdf(content)
            except RasterizeError as exc:
                raise InvoiceExtractionError(f"No se pudo rasterizar el PDF: {exc}") from exc
            return [self._data_uri("image/png", png) for png in pages]
        return [self._data_uri(content_type, content)]

    @staticmethod
    def _data_uri(mime: str, data: bytes) -> str:
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def build_azure_openai_extractor(settings: Any) -> InvoiceExtractor:
    """Extractor candidato del ranking (S4.8): gpt-5.1 vía Azure OpenAI."""
    return AzureOpenAIInvoiceExtractor(
        settings.azure_openai_endpoint,
        settings.azure_openai_key,
        settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
    )

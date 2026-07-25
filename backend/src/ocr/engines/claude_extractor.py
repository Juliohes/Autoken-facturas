"""Adaptador de extracción a JSON estructurado con Claude (Vertex AI) (S4.8, ranking multi-modelo).

Implementa `ocr.extraction.InvoiceExtractor` con el mismo prompt/parseo compartidos que Gemini
(`ocr.extraction_json`), pero con el SDK y la autenticación de `ocr/engines/claude_vertex.py`
(motor del bench): mismo proyecto/credenciales de Vertex, `AsyncAnthropicVertex`. Claude acepta PDF
nativo (bloque `document`), a diferencia de gpt-visión.

No se ejerce en CI: los tests inyectan un doble del cliente. Cualquier fallo del SDK, del contenido
o del parseo del JSON se traduce a `InvoiceExtractionError`; nunca cruza una excepción cruda.
"""

from __future__ import annotations

import base64
from typing import Any

from ocr.extraction import ExtractedInvoice, InvoiceExtractionError, InvoiceExtractor
from ocr.extraction_json import EXTRACTION_PROMPT, parse_structured_invoice

__all__ = ["ClaudeInvoiceExtractor", "build_claude_extractor"]

_VERTEX_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)
_MAX_OUTPUT_TOKENS = 4000
_ENGINE_NAME = "claude-vertex"

_IMAGE_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
_SUPPORTED_CONTENT_TYPES: frozenset[str] = _IMAGE_CONTENT_TYPES | {"application/pdf"}


class ClaudeInvoiceExtractor:
    """Extractor real basado en Claude (Vertex AI), prompteado a JSON estructurado."""

    def __init__(
        self,
        *,
        model: str,
        project: str | None,
        location: str,
        credentials_path: str | None,
        prompt: str = EXTRACTION_PROMPT,
        max_tokens: int = _MAX_OUTPUT_TOKENS,
        client: Any | None = None,
    ) -> None:
        """Crea el extractor. `client` permite inyectar un doble en test (no se llama a la red)."""
        if client is None and (not project or not credentials_path):
            raise InvoiceExtractionError(
                "Faltan las credenciales de Vertex "
                "(GOOGLE_CLOUD_PROJECT / GOOGLE_APPLICATION_CREDENTIALS)"
            )
        self._model = model
        self._project = project
        self._location = location
        self._credentials_path = credentials_path
        self._prompt = prompt
        self._max_tokens = max_tokens
        self._client = client  # construcción perezosa del cliente real

    async def extract(self, content: bytes, content_type: str) -> ExtractedInvoice:
        """Manda el documento a Claude pidiendo JSON y lo normaliza a `ExtractedInvoice`."""
        if content_type not in _SUPPORTED_CONTENT_TYPES:
            raise InvoiceExtractionError(
                f"Tipo de contenido no soportado por el motor: {content_type}"
            )

        messages = [
            {
                "role": "user",
                "content": [
                    self._document_block(content, content_type),
                    {"type": "text", "text": self._prompt},
                ],
            }
        ]
        try:
            client = self._ensure_client()
            message = await client.messages.create(
                model=self._model, max_tokens=self._max_tokens, messages=messages
            )
        except Exception as exc:  # frontera del proveedor: nada crudo cruza al llamador
            raise InvoiceExtractionError(f"Claude falló al extraer la factura: {exc}") from exc

        payload = self._text_payload(message)
        model_version = getattr(message, "model", None) or self._model
        return parse_structured_invoice(payload, engine=_ENGINE_NAME, model=model_version)

    def _document_block(self, content: bytes, content_type: str) -> dict[str, Any]:
        encoded = base64.b64encode(content).decode("ascii")
        if content_type == "application/pdf":
            source = {"type": "base64", "media_type": "application/pdf", "data": encoded}
            return {"type": "document", "source": source}
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": content_type, "data": encoded},
        }

    @staticmethod
    def _text_payload(message: Any) -> str | None:
        blocks = getattr(message, "content", None) or []
        text = "".join(getattr(b, "text", "") for b in blocks if getattr(b, "type", None) == "text")
        return text or None

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = self._make_client()
        return self._client

    def _make_client(self) -> Any:
        from anthropic import AsyncAnthropicVertex
        from google.oauth2 import service_account

        assert self._project is not None  # garantizado por la validación del __init__
        credentials = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            self._credentials_path or "", scopes=list(_VERTEX_SCOPES)
        )
        return AsyncAnthropicVertex(
            project_id=self._project, region=self._location, credentials=credentials
        )


def build_claude_extractor(settings: Any) -> InvoiceExtractor:
    """Extractor candidato del ranking (S4.8): Claude vía Vertex, mismas credenciales que Gemini."""
    return ClaudeInvoiceExtractor(
        model=settings.claude_model,
        project=settings.google_cloud_project,
        location=settings.claude_location,
        credentials_path=settings.google_application_credentials,
    )

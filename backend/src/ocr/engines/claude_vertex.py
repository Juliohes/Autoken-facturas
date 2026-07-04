"""Motor de lectura OCR basado en Claude (VLM) vía Vertex AI.

Candidato del bench de Fase 1. Como Gemini, no es OCR nativo: es un modelo multimodal al que se le
manda la imagen/PDF con un prompt de transcripción fiel a markdown, sin inventar (regla
anti-alucinación). A diferencia de gpt-visión, Claude **acepta PDF nativo** (bloque `document`),
así que no necesita rasterización previa. Normaliza la respuesta a `OcrResult` (una sola página) y
traduce fallos del SDK a `ClaudeOcrError`.

SDK: `anthropic[vertex]` (`AsyncAnthropicVertex`, `client.messages.create`). Autenticación por
service account (JSON en `GOOGLE_APPLICATION_CREDENTIALS`), misma cuenta Google que Gemini. El
proyecto y las credenciales son secretos (en el `.env`). La región y el id de modelo no lo son,
pero el id **debe** casar con el disponible en Vertex (se ajusta en el `.env` si hace falta).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropicVertex
from google.oauth2 import service_account

from ocr.engines.base import OcrEngine, OcrError, OcrPage, OcrResult

__all__ = ["ClaudeVertexEngine", "ClaudeOcrError", "OCR_PROMPT"]

# Mismo espíritu de transcripción fiel que el resto de VLM (copia local para no acoplar motores).
OCR_PROMPT = (
    "Eres un OCR de facturas. Transcribe TODO el contenido del documento a Markdown, "
    "respetando tablas, importes, fechas e identificadores fiscales tal como aparecen. "
    "No inventes ni completes datos: si algo es ilegible, déjalo en blanco. "
    "Devuelve solo el Markdown, sin comentarios ni explicaciones."
)

_VERTEX_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)
_MAX_OUTPUT_TOKENS = 4000

# Tipos soportados. Claude acepta PDF nativo (bloque document) además de imágenes.
_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


class ClaudeOcrError(OcrError):
    """Fallo del motor Claude: credenciales, tipo no soportado o error de la API de Vertex."""


class ClaudeVertexEngine(OcrEngine):
    """Adaptador de Claude (VLM) a la interfaz común `OcrEngine`."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        project: str | None,
        location: str,
        credentials_path: str | None = None,
        prompt: str = OCR_PROMPT,
        max_tokens: int = _MAX_OUTPUT_TOKENS,
        client: Any | None = None,
    ) -> None:
        """Crea el motor. `client` permite inyectar un doble en test (no se llama a la red)."""
        if client is None and (not project or not credentials_path):
            raise ClaudeOcrError(
                "Faltan las credenciales de Vertex "
                "(GOOGLE_CLOUD_PROJECT / GOOGLE_APPLICATION_CREDENTIALS)"
            )
        self._name = name
        self._model = model
        self._project = project
        self._location = location
        self._credentials_path = credentials_path
        self._prompt = prompt
        self._max_tokens = max_tokens
        self._client = client  # construcción perezosa del cliente real

    @property
    def name(self) -> str:
        return self._name

    async def extract(self, file_path: str | Path) -> OcrResult:
        """Manda el documento a Claude y devuelve el markdown transcrito, normalizado."""
        path = Path(file_path)
        if not path.is_file():
            raise ClaudeOcrError(f"No existe el fichero a procesar: {path}")

        messages = [
            {
                "role": "user",
                "content": [self._document_block(path), {"type": "text", "text": self._prompt}],
            }
        ]
        try:
            client = self._ensure_client()
            message = await client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                messages=messages,
            )
        except ClaudeOcrError:
            raise
        except Exception as exc:  # frontera del proveedor: nada crudo cruza hacia el llamador
            raise ClaudeOcrError(f"Claude falló al procesar {path.name}: {exc}") from exc

        return self._parse(message)

    def _document_block(self, path: Path) -> dict[str, Any]:
        """Bloque de contenido: `document` para PDF, `image` para imágenes (base64)."""
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        if path.suffix.lower() == ".pdf":
            source = {"type": "base64", "media_type": "application/pdf", "data": encoded}
            return {"type": "document", "source": source}
        mime = _IMAGE_MIME.get(path.suffix.lower())
        if mime is None:
            raise ClaudeOcrError(
                f"Tipo de fichero no soportado por el motor: {path.suffix or '(sin extensión)'}"
            )
        return {"type": "image", "source": {"type": "base64", "media_type": mime, "data": encoded}}

    def _ensure_client(self) -> Any:
        if self._client is None:
            self._client = self._make_client()
        return self._client

    def _make_client(self) -> AsyncAnthropicVertex:
        # Garantizado por la validación del __init__ cuando no se inyecta cliente.
        assert self._project is not None
        credentials = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            self._credentials_path or "", scopes=list(_VERTEX_SCOPES)
        )
        return AsyncAnthropicVertex(
            project_id=self._project,
            region=self._location,
            credentials=credentials,
        )

    def _parse(self, message: Any) -> OcrResult:
        """Normaliza la respuesta de Claude a `OcrResult` (una sola página)."""
        blocks = getattr(message, "content", None) or []
        markdown = "".join(
            getattr(b, "text", "") for b in blocks if getattr(b, "type", None) == "text"
        )
        usage = self._usage(getattr(message, "usage", None))
        return OcrResult(
            engine=self.name,
            model=getattr(message, "model", None) or self._model,
            pages=(OcrPage(index=0, markdown=markdown),),
            usage=usage,
            raw={"model": getattr(message, "model", None), "usage": usage},
        )

    @staticmethod
    def _usage(usage: Any) -> dict[str, Any] | None:
        if usage is None:
            return None
        if hasattr(usage, "model_dump"):
            dumped: dict[str, Any] = usage.model_dump()
            return dumped
        return {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }

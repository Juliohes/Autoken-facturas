"""Motor de lectura OCR basado en Google Gemini (VLM) vía Vertex AI.

Candidatos del bench de Fase 1: Gemini 3 Flash y Gemini 3 Pro. A diferencia de Mistral OCR 4 o
Azure DocIntel, Gemini no es una API OCR nativa: es un modelo multimodal al que se le manda la
imagen/PDF junto a un prompt que le pide transcribir la factura a markdown, fielmente y sin inventar
(regla anti-alucinación: lo ilegible se deja en blanco, no se rellena). Este adaptador normaliza la
respuesta a `OcrResult` (una sola página, el VLM no separa páginas) y traduce cualquier fallo del
SDK a `GeminiOcrError`.

SDK: `google-genai` v2 con backend Vertex (`genai.Client(vertexai=True, project, location,
credentials)`), ruta async `client.aio.models.generate_content`. Autenticación por service account
(JSON en `GOOGLE_APPLICATION_CREDENTIALS`). Proyecto y credenciales son secretos (en el `.env`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from google.oauth2 import service_account

from ocr.engines.base import OcrEngine, OcrError, OcrPage, OcrResult

__all__ = ["GeminiEngine", "GeminiOcrError", "OCR_PROMPT"]

# Prompt de transcripción. Insiste en fidelidad y en no inventar: lo que no se lea, se deja vacío.
OCR_PROMPT = (
    "Eres un OCR de facturas. Transcribe TODO el contenido del documento a Markdown, "
    "respetando tablas, importes, fechas e identificadores fiscales tal como aparecen. "
    "No inventes ni completes datos: si algo es ilegible, déjalo en blanco. "
    "Devuelve solo el Markdown, sin comentarios ni explicaciones."
)

# Scope mínimo para llamar a Vertex AI con la service account.
_VERTEX_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

# Tipos de fichero soportados y su MIME (las facturas del POC son JPEG/PNG/PDF).
_MIME_BY_SUFFIX = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class GeminiOcrError(OcrError):
    """Fallo del motor Gemini: credenciales, tipo no soportado o error de la API de Vertex."""


class GeminiEngine(OcrEngine):
    """Adaptador de Gemini (VLM) a la interfaz común `OcrEngine`."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        project: str | None,
        location: str,
        credentials_path: str | None = None,
        prompt: str = OCR_PROMPT,
        client: Any | None = None,
    ) -> None:
        """Crea el motor. `client` permite inyectar un doble en test (no se llama a la red)."""
        if client is None and (not project or not credentials_path):
            raise GeminiOcrError(
                "Faltan las credenciales de Vertex/Gemini "
                "(GOOGLE_CLOUD_PROJECT / GOOGLE_APPLICATION_CREDENTIALS)"
            )
        self._name = name
        self._model = model
        self._project = project
        self._location = location
        self._credentials_path = credentials_path
        self._prompt = prompt
        # El cliente real se construye de forma perezosa (parsea el JSON de la service account y
        # abre transporte): así el registro puede enumerar motores sin tocar credenciales ni red.
        self._client = client

    @property
    def name(self) -> str:
        return self._name

    async def extract(self, file_path: str | Path) -> OcrResult:
        """Manda el documento a Gemini y devuelve el markdown transcrito, normalizado."""
        path = Path(file_path)
        if not path.is_file():
            raise GeminiOcrError(f"No existe el fichero a procesar: {path}")

        mime = self._mime_for(path)
        part = types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)
        config = types.GenerateContentConfig(temperature=0.0)

        try:
            client = self._ensure_client()
            response = await client.aio.models.generate_content(
                model=self._model,
                contents=[part, self._prompt],
                config=config,
            )
        except GeminiOcrError:
            raise
        except Exception as exc:  # frontera del proveedor: nada crudo cruza hacia el llamador
            raise GeminiOcrError(f"Gemini falló al procesar {path.name}: {exc}") from exc

        return self._parse(response)

    def ensure_client(self) -> Any:
        """Cliente Vertex (perezoso), público para reutilizar credenciales/transporte.

        Otros adaptadores del módulo OCR (p. ej. el extractor a JSON estructurado de S2.3) arman
        la MISMA conexión Vertex sin duplicar el manejo de la service account: componen un
        `GeminiEngine` y le piden su cliente por aquí.
        """
        return self._ensure_client()

    def _ensure_client(self) -> Any:
        """Devuelve el cliente, construyéndolo la primera vez (perezoso)."""
        if self._client is None:
            self._client = self._make_client()
        return self._client

    def _make_client(self) -> genai.Client:
        credentials = service_account.Credentials.from_service_account_file(  # type: ignore[no-untyped-call]
            self._credentials_path or "", scopes=list(_VERTEX_SCOPES)
        )
        return genai.Client(
            vertexai=True,
            project=self._project,
            location=self._location,
            credentials=credentials,
        )

    def _mime_for(self, path: Path) -> str:
        """Resuelve el MIME por extensión; tipo no soportado -> `GeminiOcrError`."""
        mime = _MIME_BY_SUFFIX.get(path.suffix.lower())
        if mime is None:
            raise GeminiOcrError(
                f"Tipo de fichero no soportado por el motor: {path.suffix or '(sin extensión)'}"
            )
        return mime

    def _parse(self, response: Any) -> OcrResult:
        """Normaliza la respuesta del VLM a `OcrResult` (una sola página)."""
        markdown = getattr(response, "text", None) or ""
        usage = self._usage(getattr(response, "usage_metadata", None))
        return OcrResult(
            engine=self.name,
            model=getattr(response, "model_version", None) or self._model,
            pages=(OcrPage(index=0, markdown=markdown),),
            usage=usage,
            raw={
                "model_version": getattr(response, "model_version", None),
                "usage": usage,
            },
        )

    @staticmethod
    def _usage(meta: Any) -> dict[str, Any] | None:
        if meta is None:
            return None
        if hasattr(meta, "model_dump"):
            dumped: dict[str, Any] = meta.model_dump()
            return dumped
        return {
            "prompt_token_count": getattr(meta, "prompt_token_count", None),
            "candidates_token_count": getattr(meta, "candidates_token_count", None),
            "total_token_count": getattr(meta, "total_token_count", None),
        }

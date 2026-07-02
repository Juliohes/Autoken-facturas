"""Motor de lectura OCR basado en Mistral OCR 4 (`mistral-ocr-4-0`).

Cabeza de serie del bench de Fase 1 (decisión de Julio, 2026-07-01). Mistral OCR 4 devuelve
markdown por página, bloques clasificados, bounding boxes y confidencias (170 idiomas). Este
adaptador normaliza esa respuesta a `OcrResult` y traduce cualquier fallo del SDK a
`MistralOcrError`, para que el orquestador del bench nunca vea excepciones crudas del proveedor.

SDK: `mistralai` v2 (`from mistralai.client import Mistral`, `client.ocr.process_async`).
API verificada contra la documentación oficial de Mistral (endpoint `POST /v1/ocr`).
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from mistralai.client import Mistral
from mistralai.client.models import DocumentURLChunkTypedDict, ImageURLChunkTypedDict

from ocr.engines.base import OcrEngine, OcrError, OcrPage, OcrResult

__all__ = ["MistralOcr4Engine", "MistralOcrError", "DEFAULT_MISTRAL_OCR_MODEL"]

# Id de modelo verificado contra la documentación de Mistral (OCR 4, lanzado 2026-06-23).
DEFAULT_MISTRAL_OCR_MODEL = "mistral-ocr-4-0"
DEFAULT_MISTRAL_OCR_TIMEOUT_S = 60

# Tipos de fichero soportados y su MIME (las facturas del POC son JPEG/PNG/PDF).
_PDF_SUFFIXES = frozenset({".pdf"})
_IMAGE_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class MistralOcrError(OcrError):
    """Fallo del motor Mistral OCR: credenciales, timeout, tipo no soportado o error de API."""


class MistralOcr4Engine(OcrEngine):
    """Adaptador de Mistral OCR 4 a la interfaz común `OcrEngine`."""

    def __init__(
        self,
        api_key: str | None,
        *,
        model: str = DEFAULT_MISTRAL_OCR_MODEL,
        timeout_s: int = DEFAULT_MISTRAL_OCR_TIMEOUT_S,
        client: Any | None = None,
    ) -> None:
        """Crea el motor. `client` permite inyectar un doble en test (no se llama a la red)."""
        if client is None and not api_key:
            raise MistralOcrError("Falta la API key de Mistral (MISTRAL_API_KEY)")
        self._model = model
        self._timeout_s = timeout_s
        self._client = client if client is not None else Mistral(api_key=api_key or "")

    @property
    def name(self) -> str:
        return "mistral-ocr-4"

    async def extract(self, file_path: str | Path) -> OcrResult:
        """Manda el documento a Mistral OCR 4 y devuelve el resultado normalizado."""
        path = Path(file_path)
        if not path.is_file():
            raise MistralOcrError(f"No existe el fichero a procesar: {path}")

        document = self._build_document(path)
        try:
            response = await self._client.ocr.process_async(
                model=self._model,
                document=document,
                include_image_base64=False,
                include_blocks=True,
                confidence_scores_granularity="page",
                timeout_ms=self._timeout_s * 1000,
            )
        except MistralOcrError:
            raise
        except Exception as exc:  # frontera del proveedor: nada crudo cruza hacia el llamador
            raise MistralOcrError(f"Mistral OCR falló al procesar {path.name}: {exc}") from exc

        return self._parse(response)

    def _build_document(self, path: Path) -> DocumentURLChunkTypedDict | ImageURLChunkTypedDict:
        """Traduce el fichero local al formato `document` de Mistral (base64 data URI)."""
        suffix = path.suffix.lower()
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        if suffix in _PDF_SUFFIXES:
            return {
                "type": "document_url",
                "document_url": f"data:application/pdf;base64,{encoded}",
            }
        mime = _IMAGE_MIME.get(suffix)
        if mime is None:
            raise MistralOcrError(
                f"Tipo de fichero no soportado por el motor: {suffix or '(sin extensión)'}"
            )
        return {"type": "image_url", "image_url": f"data:{mime};base64,{encoded}"}

    def _parse(self, response: Any) -> OcrResult:
        """Normaliza la respuesta del SDK a `OcrResult`, conservando el crudo en `raw`."""
        raw: dict[str, Any] = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )
        pages = tuple(self._parse_page(page) for page in raw.get("pages") or [])
        return OcrResult(
            engine=self.name,
            model=raw.get("model") or self._model,
            pages=pages,
            usage=raw.get("usage_info"),
            raw=raw,
        )

    @staticmethod
    def _parse_page(page: dict[str, Any]) -> OcrPage:
        dimensions = page.get("dimensions") or {}
        return OcrPage(
            index=int(page.get("index") or 0),
            markdown=page.get("markdown") or "",
            width=dimensions.get("width"),
            height=dimensions.get("height"),
        )

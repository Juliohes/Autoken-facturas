"""Motor de lectura OCR basado en Azure AI Document Intelligence (antes Form Recognizer).

Candidato del bench de Fase 1. Se usa el modelo `prebuilt-layout` con salida **markdown** (incluye
tablas), para que la comparación con Mistral OCR 4 sea justa: ambos devuelven markdown por
documento. El adaptador normaliza la respuesta a `OcrResult` y traduce fallos del SDK a `OcrError`.

SDK: `azure-ai-documentintelligence` v1 (cliente async `DocumentIntelligenceClient`,
`begin_analyze_document` + `await poller.result()`). Endpoint/clave son secretos (van en el `.env`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from azure.ai.documentintelligence.aio import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeDocumentRequest,
    DocumentContentFormat,
)
from azure.core.credentials import AzureKeyCredential

from ocr.engines.base import OcrEngine, OcrError, OcrPage, OcrResult

__all__ = ["AzureDocIntelEngine", "AzureDocIntelError", "DEFAULT_DOCINTEL_MODEL"]

# Modelo de lectura por defecto: layout devuelve markdown con tablas (comparable a Mistral OCR 4).
DEFAULT_DOCINTEL_MODEL = "prebuilt-layout"

# Azure separa las páginas en el markdown con este marcador de comentario.
_PAGE_BREAK = "<!-- PageBreak -->"


class AzureDocIntelError(OcrError):
    """Fallo del motor Azure DocIntel: credenciales, tipo no soportado o error de API."""


class AzureDocIntelEngine(OcrEngine):
    """Adaptador de Azure Document Intelligence a la interfaz común `OcrEngine`."""

    def __init__(
        self,
        endpoint: str | None,
        key: str | None,
        *,
        model: str = DEFAULT_DOCINTEL_MODEL,
        client: Any | None = None,
    ) -> None:
        """Crea el motor. `client` permite inyectar un doble en test (no se llama a la red)."""
        if client is None and (not endpoint or not key):
            raise AzureDocIntelError(
                "Faltan las credenciales de Azure DocIntel "
                "(AZURE_DOCINTEL_ENDPOINT / AZURE_DOCINTEL_KEY)"
            )
        self._endpoint = endpoint
        self._key = key
        self._model = model
        self._client = client

    @property
    def name(self) -> str:
        return "azure-docintel"

    async def extract(self, file_path: str | Path) -> OcrResult:
        """Manda el documento a Azure DocIntel y devuelve el resultado normalizado."""
        path = Path(file_path)
        if not path.is_file():
            raise AzureDocIntelError(f"No existe el fichero a procesar: {path}")
        data = path.read_bytes()

        try:
            if self._client is not None:  # cliente inyectado en test
                result = await self._analyze(self._client, data)
            else:
                async with self._make_client() as client:
                    result = await self._analyze(client, data)
        except AzureDocIntelError:
            raise
        except Exception as exc:  # frontera del proveedor: nada crudo cruza hacia el llamador
            raise AzureDocIntelError(
                f"Azure DocIntel falló al procesar {path.name}: {exc}"
            ) from exc

        return self._parse(result)

    def _make_client(self) -> DocumentIntelligenceClient:
        return DocumentIntelligenceClient(
            endpoint=self._endpoint or "",
            credential=AzureKeyCredential(self._key or ""),
        )

    async def _analyze(self, client: Any, data: bytes) -> Any:
        poller = await client.begin_analyze_document(
            self._model,
            AnalyzeDocumentRequest(bytes_source=data),
            output_content_format=DocumentContentFormat.MARKDOWN,
        )
        return await poller.result()

    def _parse(self, result: Any) -> OcrResult:
        """Normaliza el `AnalyzeResult` a `OcrResult`."""
        content: str = result.content or ""
        pages = self._split_pages(content, list(result.pages or []))
        return OcrResult(
            engine=self.name,
            model=getattr(result, "model_id", None) or self._model,
            pages=pages,
            usage={"pages": len(result.pages or [])},
            raw={
                "model_id": getattr(result, "model_id", None),
                "content_format": str(getattr(result, "content_format", "")),
                "page_count": len(result.pages or []),
            },
        )

    @staticmethod
    def _split_pages(content: str, pages: list[Any]) -> tuple[OcrPage, ...]:
        """Reparte el markdown por página con el marcador de Azure; si no cuadra, todo en una."""
        parts = content.split(_PAGE_BREAK)
        if pages and len(parts) == len(pages):
            return tuple(
                OcrPage(
                    index=(getattr(page, "page_number", None) or i + 1) - 1,
                    markdown=part.strip(),
                    width=getattr(page, "width", None),
                    height=getattr(page, "height", None),
                )
                for i, (part, page) in enumerate(zip(parts, pages, strict=False))
            )
        first = pages[0] if pages else None
        return (
            OcrPage(
                index=0,
                markdown=content,
                width=getattr(first, "width", None),
                height=getattr(first, "height", None),
            ),
        )

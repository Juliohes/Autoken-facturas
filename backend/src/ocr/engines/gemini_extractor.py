"""Adaptador real de extracción a JSON estructurado con Gemini (Vertex AI) (S2.3, ADR-0016).

Implementa la abstracción `ocr.extraction.InvoiceExtractor` con el motor de lectura del bench
(ADR-0007), pero prompteado para devolver **JSON estructurado** (los campos de oro con confianza por
campo), no una transcripción libre a Markdown como la capa de bench (`ocr/engines/gemini.py`). Vive
en `ocr/engines` (infraestructura del proveedor) para que el contrato puro (`ocr/extraction.py`) y
los módulos de dominio (`ocr/analysis`, `ocr/arbiter`) no arrastren el SDK ni credenciales Vertex.

El prompt y el parseo del JSON son compartidos (`ocr.extraction_json`, extraído en S4.8) con los
demás motores "promptables" del ranking multi-modelo (Claude, gpt-5.1): solo cambia aquí cómo se
manda el documento a la API de Gemini y cómo se lee el texto de vuelta.

No se ejerce en CI: los tests inyectan un doble. Cualquier fallo del SDK, del contenido o del parseo
del JSON se traduce a `InvoiceExtractionError`; nunca cruza una excepción cruda del SDK al llamador.
"""

from __future__ import annotations

from typing import Any

from ocr.extraction import DocumentPage, ExtractedInvoice, InvoiceExtractionError, InvoiceExtractor
from ocr.extraction_json import EXTRACTION_PROMPT, parse_structured_invoice

__all__ = [
    "GeminiInvoiceExtractor",
    "build_default_extractor",
    "build_gemini_pro_extractor",
    "EXTRACTION_PROMPT",
]

# MIME que el motor de visión acepta (facturas del intake: JPEG/PNG/PDF).
_SUPPORTED_CONTENT_TYPES: frozenset[str] = frozenset(
    {"image/jpeg", "image/png", "application/pdf", "image/webp"}
)


class GeminiInvoiceExtractor:
    """Extractor real basado en Gemini (Vertex AI), prompteado a JSON estructurado.

    Reutiliza la construcción de credenciales/cliente Vertex de `GeminiEngine` (mismo proyecto y
    service account que el bench). No se ejerce en CI: los tests inyectan un doble. Cualquier fallo
    del SDK, del contenido o del parseo del JSON se traduce a `InvoiceExtractionError`.

    `engine`: nombre estable del motor concreto (S4.8, ranking multi-modelo) — "gemini-3-flash"
    (producción) o "gemini-3-pro" (candidato del ranking), mismo modelo de cliente Vertex.
    """

    def __init__(
        self,
        *,
        engine: str,
        model: str,
        project: str | None,
        location: str,
        credentials_path: str | None,
        prompt: str = EXTRACTION_PROMPT,
    ) -> None:
        # La validación de credenciales y la construcción perezosa del cliente viven en
        # `GeminiEngine` (fuente única): se compone en vez de duplicarlas.
        from ocr.engines.gemini import GeminiEngine, GeminiOcrError

        try:
            self._engine = GeminiEngine(
                name="gemini-invoice-extractor",
                model=model,
                project=project,
                location=location,
                credentials_path=credentials_path,
            )
        except GeminiOcrError as exc:  # faltan credenciales: es un fallo de extracción configurable
            raise InvoiceExtractionError(str(exc)) from exc
        self._name = engine
        self._model = model
        self._prompt = prompt

    async def extract(self, content: bytes, content_type: str) -> ExtractedInvoice:
        """Manda el documento a Gemini pidiendo JSON y lo normaliza a `ExtractedInvoice`."""
        return await self.extract_pages([DocumentPage(content, content_type)])

    async def extract_pages(self, pages: list[DocumentPage]) -> ExtractedInvoice:
        """Manda todas las imágenes ordenadas en una sola petición al modelo."""
        if not pages:
            raise InvoiceExtractionError("El documento no contiene páginas")
        if any(page.content_type not in _SUPPORTED_CONTENT_TYPES for page in pages):
            raise InvoiceExtractionError("Tipo de contenido no soportado por el motor")

        from google.genai import types

        parts = [
            types.Part.from_bytes(data=page.content, mime_type=page.content_type) for page in pages
        ]
        config = types.GenerateContentConfig(temperature=0.0, response_mime_type="application/json")
        try:
            client = self._engine.ensure_client()
            response = await client.aio.models.generate_content(
                model=self._model, contents=[*parts, self._prompt], config=config
            )
        except Exception as exc:  # frontera del proveedor: nada crudo cruza al llamador
            raise InvoiceExtractionError(f"Gemini falló al extraer la factura: {exc}") from exc

        payload = getattr(response, "text", None)
        model_version = getattr(response, "model_version", None) or self._model
        return parse_structured_invoice(payload, engine=self._name, model=model_version)


def build_default_extractor(settings: Any) -> InvoiceExtractor:
    """Extractor de producción: gemini-3-flash a JSON estructurado (ADR-0016).

    Toma modelo, proyecto, región y credenciales de la config (los mismos que el bench Vertex).
    No se llama en CI (los tests inyectan un doble); en integración/staging lee facturas reales.
    """
    return GeminiInvoiceExtractor(
        engine="gemini-3-flash",
        model=settings.gemini_flash_model,
        project=settings.google_cloud_project,
        location=settings.gemini_location,
        credentials_path=settings.google_application_credentials,
    )


def build_gemini_pro_extractor(settings: Any) -> InvoiceExtractor:
    """Extractor candidato del ranking (S4.8): gemini-3-pro, mismo cliente que Flash (S2.3)."""
    return GeminiInvoiceExtractor(
        engine="gemini-3-pro",
        model=settings.gemini_pro_model,
        project=settings.google_cloud_project,
        location=settings.gemini_location,
        credentials_path=settings.google_application_credentials,
    )

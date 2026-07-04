"""Registro de motores de lectura OCR del bench.

Punto único donde se decide qué motor es la **cabeza de serie** (por defecto). Hoy es Mistral
OCR 4 (decisión de Julio, 2026-07-01). El ganador formal de producción lo fija el bench con las
20 facturas reales (ADR-0007); cuando entren más motores (DocIntel, PaddleOCR, Qwen...) se
registran aquí con la misma interfaz `OcrEngine`.
"""

from __future__ import annotations

from ocr.engines.azure_docintel import AzureDocIntelEngine
from ocr.engines.base import OcrEngine
from ocr.engines.gemini import GeminiEngine
from ocr.engines.mistral_ocr4 import MistralOcr4Engine
from shared.config import Settings

__all__ = [
    "build_default_reading_engine",
    "build_docintel_engine",
    "build_gemini_engines",
]


def build_default_reading_engine(settings: Settings) -> OcrEngine:
    """Construye el motor de lectura por defecto del bench a partir de la configuración.

    Cabeza de serie: Mistral OCR 4. Lanza `MistralOcrError` si falta la `MISTRAL_API_KEY`.
    """
    return MistralOcr4Engine(
        api_key=settings.mistral_api_key,
        model=settings.mistral_ocr_model,
        timeout_s=settings.mistral_ocr_timeout,
    )


def build_docintel_engine(settings: Settings) -> OcrEngine:
    """Construye el motor Azure DocIntel. Lanza `AzureDocIntelError` si faltan las credenciales."""
    return AzureDocIntelEngine(
        endpoint=settings.azure_docintel_endpoint,
        key=settings.azure_docintel_key,
        model=settings.azure_docintel_model,
    )


def build_gemini_engines(settings: Settings) -> list[OcrEngine]:
    """Construye los dos candidatos Gemini (Flash y Pro) que comparten proyecto/credenciales.

    Lanza `GeminiOcrError` si faltan las credenciales de Vertex (así el runner los omite juntos).
    """
    tiers = (
        ("gemini-3-flash", settings.gemini_flash_model),
        ("gemini-3-pro", settings.gemini_pro_model),
    )
    return [
        GeminiEngine(
            name=name,
            model=model,
            project=settings.google_cloud_project,
            location=settings.gemini_location,
            credentials_path=settings.google_application_credentials,
        )
        for name, model in tiers
    ]

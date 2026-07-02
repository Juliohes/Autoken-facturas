"""Registro de motores de lectura OCR del bench.

Punto único donde se decide qué motor es la **cabeza de serie** (por defecto). Hoy es Mistral
OCR 4 (decisión de Julio, 2026-07-01). El ganador formal de producción lo fija el bench con las
20 facturas reales (ADR-0007); cuando entren más motores (DocIntel, PaddleOCR, Qwen...) se
registran aquí con la misma interfaz `OcrEngine`.
"""

from __future__ import annotations

from ocr.engines.base import OcrEngine
from ocr.engines.mistral_ocr4 import MistralOcr4Engine
from shared.config import Settings

__all__ = ["build_default_reading_engine"]


def build_default_reading_engine(settings: Settings) -> OcrEngine:
    """Construye el motor de lectura por defecto del bench a partir de la configuración.

    Cabeza de serie: Mistral OCR 4. Lanza `MistralOcrError` si falta la `MISTRAL_API_KEY`.
    """
    return MistralOcr4Engine(
        api_key=settings.mistral_api_key,
        model=settings.mistral_ocr_model,
        timeout_s=settings.mistral_ocr_timeout,
    )

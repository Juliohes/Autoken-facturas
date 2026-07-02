"""Motores de lectura OCR del bench (Fase 1). Ver `docs/specs/1.2-mistral-ocr4-engine.md`."""

from ocr.engines.base import OcrEngine, OcrError, OcrPage, OcrResult
from ocr.engines.mistral_ocr4 import (
    DEFAULT_MISTRAL_OCR_MODEL,
    MistralOcr4Engine,
    MistralOcrError,
)
from ocr.engines.registry import build_default_reading_engine

__all__ = [
    "OcrEngine",
    "OcrError",
    "OcrPage",
    "OcrResult",
    "MistralOcr4Engine",
    "MistralOcrError",
    "DEFAULT_MISTRAL_OCR_MODEL",
    "build_default_reading_engine",
]

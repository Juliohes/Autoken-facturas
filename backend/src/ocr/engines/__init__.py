"""Motores de lectura OCR del bench (Fase 1). Ver `docs/specs/1.2-mistral-ocr4-engine.md`."""

from ocr.engines.azure_docintel import (
    DEFAULT_DOCINTEL_MODEL,
    AzureDocIntelEngine,
    AzureDocIntelError,
)
from ocr.engines.azure_openai import AzureOpenAIEngine, AzureOpenAIError
from ocr.engines.base import OcrEngine, OcrError, OcrPage, OcrResult
from ocr.engines.gemini import GeminiEngine, GeminiOcrError
from ocr.engines.mistral_ocr4 import (
    DEFAULT_MISTRAL_OCR_MODEL,
    MistralOcr4Engine,
    MistralOcrError,
)
from ocr.engines.registry import (
    build_azure_openai_engine,
    build_default_reading_engine,
    build_docintel_engine,
    build_gemini_engines,
)

__all__ = [
    "OcrEngine",
    "OcrError",
    "OcrPage",
    "OcrResult",
    "MistralOcr4Engine",
    "MistralOcrError",
    "DEFAULT_MISTRAL_OCR_MODEL",
    "AzureDocIntelEngine",
    "AzureDocIntelError",
    "DEFAULT_DOCINTEL_MODEL",
    "GeminiEngine",
    "GeminiOcrError",
    "AzureOpenAIEngine",
    "AzureOpenAIError",
    "build_default_reading_engine",
    "build_docintel_engine",
    "build_gemini_engines",
    "build_azure_openai_engine",
]

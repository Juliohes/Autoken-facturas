"""Construcción del extractor primario de producción según R-033."""

from __future__ import annotations

from typing import Any

from ocr.engines.gemini_extractor import build_gemini_model_extractor
from ocr.engines.mistral_extractor import MistralInvoiceExtractor
from ocr.extraction import InvoiceExtractionError, InvoiceExtractor
from ocr.policy import OcrPolicy

__all__ = ["build_fallback_extractor", "build_production_extractor"]

_GEMINI_ENGINES = frozenset(
    {"gemini-3-flash", "gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"}
)
_MISTRAL_ENGINE = "mistral-ocr-4"


def build_production_extractor(settings: Any, policy: OcrPolicy) -> InvoiceExtractor:
    """Construye exactamente el primario configurado, nunca un candidato del laboratorio."""
    return _build_extractor(settings, policy.primary_engine, policy.primary_model)


def build_fallback_extractor(settings: Any, policy: OcrPolicy) -> InvoiceExtractor:
    """Construye el fallback configurado; no permite activar uno incompleto."""
    if (
        not policy.fallback_enabled
        or policy.fallback_engine is None
        or policy.fallback_model is None
    ):
        raise InvoiceExtractionError("fallback OCR no está habilitado")
    return _build_extractor(settings, policy.fallback_engine, policy.fallback_model)


def _build_extractor(settings: Any, engine: str, model: str) -> InvoiceExtractor:
    if engine in _GEMINI_ENGINES:
        return build_gemini_model_extractor(
            settings,
            engine=engine,
            model=model,
        )
    if engine == _MISTRAL_ENGINE:
        return MistralInvoiceExtractor(
            settings.mistral_api_key,
            model=model,
            timeout_s=settings.mistral_ocr_timeout,
        )
    raise InvoiceExtractionError("OCR engine no soportado por producción")

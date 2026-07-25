"""Registro de motores candidatos del ranking multi-modelo (S4.8).

Construye los 6 extractores estructurados (Gemini Flash/Pro, Claude, gpt-5.1, Azure DocIntel,
Mistral) de forma TOLERANTE: un motor sin sus credenciales en el `.env` simplemente no se incluye
(spec C3, sin error visible) — mismo criterio ya establecido en `ocr/engines/registry.py` para el
bench de la Fase 1 ("cada motor sin credenciales se omite con un aviso").

Gemini Flash se separa del resto (`build_default_ranking_extractor` vs
`build_additional_ranking_extractors`) porque `jobs/ocr.py::run_ocr` YA calcula esa lectura para
la extracción principal: reutilizarla evita pagar la llamada a Gemini Flash dos veces por factura
(hallazgo crítico de la auditoría S4.8 — el mismo tipo de bug de coste duplicado que ya se corrigió
en S2.10 para `run_ocr_comparison`).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog

from ocr.engines.azure_docintel_extractor import build_azure_docintel_extractor
from ocr.engines.azure_openai_extractor import build_azure_openai_extractor
from ocr.engines.claude_extractor import build_claude_extractor
from ocr.engines.gemini_extractor import build_default_extractor, build_gemini_pro_extractor
from ocr.engines.mistral_extractor import build_mistral_extractor
from ocr.extraction import InvoiceExtractionError, InvoiceExtractor

logger = structlog.get_logger(__name__)

__all__ = [
    "build_additional_ranking_extractors",
    "build_default_ranking_extractor",
    "build_ranking_extractors",
]

_ADDITIONAL_BUILDERS: tuple[Callable[[Any], InvoiceExtractor], ...] = (
    build_gemini_pro_extractor,
    build_claude_extractor,
    build_azure_openai_extractor,
    build_azure_docintel_extractor,
    build_mistral_extractor,
)


def build_default_ranking_extractor(settings: Any) -> InvoiceExtractor | None:
    """El motor "por defecto" (Gemini Flash): `None` si no tiene credenciales configuradas."""
    try:
        return build_default_extractor(settings)
    except InvoiceExtractionError as exc:
        logger.warning(
            "ranking.engine_unavailable", builder=build_default_extractor.__name__, reason=str(exc)
        )
        return None


def build_additional_ranking_extractors(settings: Any) -> list[InvoiceExtractor]:
    """Los 5 motores adicionales al de por defecto; tolerante igual que `build_ranking_extractors`
    (motor sin credenciales -> se omite sin error, spec C3)."""
    extractors: list[InvoiceExtractor] = []
    for builder in _ADDITIONAL_BUILDERS:
        try:
            extractors.append(builder(settings))
        except InvoiceExtractionError as exc:
            logger.warning("ranking.engine_unavailable", builder=builder.__name__, reason=str(exc))
    return extractors


def build_ranking_extractors(settings: Any) -> list[InvoiceExtractor]:
    """Los 6 motores juntos (usado por el backfill, sin ninguna lectura previa que reutilizar)."""
    default = build_default_ranking_extractor(settings)
    extractors = [default] if default is not None else []
    extractors.extend(build_additional_ranking_extractors(settings))
    return extractors

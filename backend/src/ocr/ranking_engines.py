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

from ocr.engines.azure_docintel_extractor import (
    ENGINE_NAME as AZURE_DOCINTEL_ENGINE_NAME,
)
from ocr.engines.azure_docintel_extractor import build_azure_docintel_extractor
from ocr.engines.azure_openai_extractor import (
    ENGINE_NAME as AZURE_OPENAI_ENGINE_NAME,
)
from ocr.engines.azure_openai_extractor import build_azure_openai_extractor
from ocr.engines.claude_extractor import ENGINE_NAME as CLAUDE_ENGINE_NAME
from ocr.engines.claude_extractor import build_claude_extractor
from ocr.engines.gemini_extractor import build_default_extractor, build_gemini_pro_extractor
from ocr.engines.mistral_extractor import ENGINE_NAME as MISTRAL_ENGINE_NAME
from ocr.engines.mistral_extractor import build_mistral_extractor
from ocr.extraction import InvoiceExtractionError, InvoiceExtractor

logger = structlog.get_logger(__name__)

__all__ = [
    "build_additional_ranking_extractors",
    "build_default_ranking_extractor",
    "build_named_ranking_extractors",
    "build_ranking_extractors",
]

_ADDITIONAL_BUILDERS: tuple[Callable[[Any], InvoiceExtractor], ...] = (
    build_gemini_pro_extractor,
    build_claude_extractor,
    build_azure_openai_extractor,
    build_azure_docintel_extractor,
    build_mistral_extractor,
)

# Nombre de motor exacto (`ExtractedInvoice.engine`) que produce cada builder -- fuente única para
# `build_named_ranking_extractors` (S6.7): los mismos nombres ya usados por cada extractor real
# (constante pública `ENGINE_NAME` de cada `ocr.engines.*_extractor`, o el literal
# `engine="gemini-3-flash"/"gemini-3-pro"` de `ocr.engines.gemini_extractor`, que no expone una
# constante propia todavía), sin reteclearlos ni arriesgarse a que diverjan en silencio del nombre
# real que cada extractor pone en su lectura (auditoría S6.7, hallazgo de SOLID/DRY).
_NAMED_BUILDERS: tuple[tuple[str, Callable[[Any], InvoiceExtractor]], ...] = (
    ("gemini-3-flash", build_default_extractor),
    ("gemini-3-pro", build_gemini_pro_extractor),
    (CLAUDE_ENGINE_NAME, build_claude_extractor),
    (AZURE_OPENAI_ENGINE_NAME, build_azure_openai_extractor),
    (AZURE_DOCINTEL_ENGINE_NAME, build_azure_docintel_extractor),
    (MISTRAL_ENGINE_NAME, build_mistral_extractor),
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


def build_named_ranking_extractors(settings: Any) -> list[tuple[str, InvoiceExtractor]]:
    """Los 6 motores CON su nombre (S6.7, `ocr.benchmark`/`jobs.ocr_benchmark`): a diferencia de
    `build_ranking_extractors` (solo usada para reconciliar la lectura por defecto, spec S4.8), el
    benchmark necesita conocer el nombre del motor AUNQUE `.extract()` falle antes de devolver
    ningún `ExtractedInvoice.engine` (C2 -- persistir una fila de error por motor caído). Tolerante
    igual que el resto de este módulo: un motor sin credenciales se omite sin error (spec C3)."""
    extractors: list[tuple[str, InvoiceExtractor]] = []
    for name, builder in _NAMED_BUILDERS:
        try:
            extractors.append((name, builder(settings)))
        except InvoiceExtractionError as exc:
            logger.warning("ranking.engine_unavailable", builder=builder.__name__, reason=str(exc))
    return extractors

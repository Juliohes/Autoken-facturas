"""Tests del registro de motores del ranking multi-modelo (S4.8).

Criterio C3: un motor sin sus credenciales configuradas se omite sin bloquear a los demás, sin
error visible. Módulo puro (construcción de extractores, sin llamar a ningún proveedor).
"""

from __future__ import annotations

import pytest

from ocr.ranking_engines import (
    build_additional_ranking_extractors,
    build_default_ranking_extractor,
    build_named_benchmark_extractors,
    build_named_ranking_extractors,
    build_ranking_extractors,
)
from shared.config import Settings


def test_c3_sin_ninguna_credencial_devuelve_lista_vacia_sin_lanzar() -> None:
    """Ningún motor configurado (`.env` vacío) -> lista vacía, nunca un error."""
    extractors = build_ranking_extractors(Settings(_env_file=None))  # type: ignore[call-arg]
    assert extractors == []


def test_c3_motores_con_credenciales_se_incluyen_los_demas_se_omiten() -> None:
    """Solo Gemini configurado (mismas credenciales Vertex que Claude) -> ambos se incluyen;
    los que exigen otras credenciales (Azure/Mistral) se omiten sin bloquear a los que sí están."""
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        google_cloud_project="autoken-ocr",
        google_application_credentials="/secrets/vertex-sa.json",
    )

    extractors = build_ranking_extractors(settings)

    names = set()
    for extractor in extractors:
        names.add(type(extractor).__name__)
    # Gemini Flash + Gemini Pro + Claude comparten credenciales Vertex: los 3 se construyen.
    assert len(extractors) == 3
    assert names == {"GeminiInvoiceExtractor", "ClaudeInvoiceExtractor"}


def test_default_y_adicionales_sin_credenciales_no_lanzan() -> None:
    """Sin ninguna credencial: el por defecto es `None`, los adicionales son una lista vacía."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert build_default_ranking_extractor(settings) is None
    assert build_additional_ranking_extractors(settings) == []


def test_default_y_adicionales_juntos_igualan_a_build_ranking_extractors() -> None:
    """El por defecto + los adicionales cubren exactamente los mismos motores que la lista de 6."""
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        google_cloud_project="autoken-ocr",
        google_application_credentials="/secrets/vertex-sa.json",
    )

    default = build_default_ranking_extractor(settings)
    additional = build_additional_ranking_extractors(settings)
    combined = ([default] if default is not None else []) + additional

    all_names = sorted(type(e).__name__ for e in build_ranking_extractors(settings))
    combined_names = sorted(type(e).__name__ for e in combined)
    assert combined_names == all_names
    assert default is not None
    assert type(default).__name__ == "GeminiInvoiceExtractor"


async def test_s6_7_el_benchmark_conserva_los_seis_motores_sin_credenciales() -> None:
    """Una configuración ausente debe dejar seis resultados de error, no sesgar el benchmark."""
    from ocr.extraction import InvoiceExtractionError

    extractors = build_named_ranking_extractors(Settings(_env_file=None))  # type: ignore[call-arg]

    assert [name for name, _ in extractors] == [
        "gemini-3-flash",
        "gemini-3-pro",
        "claude-vertex",
        "gpt-5.1",
        "azure-docintel",
        "mistral-ocr-4",
    ]
    for _, extractor in extractors:
        with pytest.raises(InvoiceExtractionError, match="engine_unavailable"):
            await extractor.extract(b"no hay llamada", "image/jpeg")


async def test_r032_fija_los_cuatro_candidatos_minimos_sin_credenciales() -> None:
    """R-032 no mezcla el ranking histórico ni reduce artificialmente la salida estructurada."""
    from ocr.extraction import InvoiceExtractionError

    extractors = build_named_benchmark_extractors(Settings(_env_file=None))  # type: ignore[call-arg]

    assert [name for name, _ in extractors] == [
        "gemini-3.5-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite",
        "mistral-ocr-4",
    ]
    for _, extractor in extractors:
        with pytest.raises(InvoiceExtractionError, match="engine_unavailable"):
            await extractor.extract(b"no hay llamada", "image/jpeg")

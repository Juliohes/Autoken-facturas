"""Tests del motor Azure Document Intelligence (candidato del bench, Fase 1).

El cliente de Azure va SIEMPRE mockeado: los tests jamás llaman a la API real (sin red en CI).
El doble reproduce la forma real del SDK v1: `begin_analyze_document` async devuelve un poller
cuyo `.result()` async entrega un `AnalyzeResult` con `content`/`pages`/`model_id`.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ocr.engines import (
    AzureDocIntelEngine,
    AzureDocIntelError,
    OcrResult,
    build_docintel_engine,
)
from shared.config import Settings


def _fake_result(content: str, pages: list[SimpleNamespace]) -> SimpleNamespace:
    """`AnalyzeResult` con la forma real del SDK: markdown en `content` y metadatos por página."""
    return SimpleNamespace(
        content=content,
        pages=pages,
        model_id="prebuilt-layout",
        content_format="markdown",
    )


def _engine_with_result(result: SimpleNamespace) -> AzureDocIntelEngine:
    poller = SimpleNamespace(result=AsyncMock(return_value=result))
    client = SimpleNamespace(begin_analyze_document=AsyncMock(return_value=poller))
    return AzureDocIntelEngine(endpoint=None, key=None, client=client)


@pytest.fixture
def factura(tmp_path: Path) -> Path:
    ruta = tmp_path / "factura.png"
    ruta.write_bytes(b"\x89PNG bytes de prueba")
    return ruta


async def test_extract_devuelve_resultado_normalizado(factura: Path) -> None:  # C1
    page = SimpleNamespace(page_number=1, width=8.5, height=11.0)
    result_engine = _engine_with_result(
        _fake_result("# Factura\nTotal: 121,00 EUR", [page])
    )

    result = await result_engine.extract(factura)

    assert isinstance(result, OcrResult)
    assert result.engine == "azure-docintel"
    assert result.model == "prebuilt-layout"
    assert result.pages[0].markdown.startswith("# Factura")
    assert result.pages[0].index == 0
    assert result.pages[0].width == 8.5
    assert "Total" in result.text
    assert result.usage == {"pages": 1}
    assert result.raw["page_count"] == 1  # el crudo del proveedor se conserva


async def test_split_de_paginas_por_marcador(factura: Path) -> None:  # C2
    content = "# Página uno\ncuerpo A<!-- PageBreak -->## Página dos\ncuerpo B"
    pages = [
        SimpleNamespace(page_number=1, width=8.5, height=11.0),
        SimpleNamespace(page_number=2, width=8.5, height=11.0),
    ]
    engine = _engine_with_result(_fake_result(content, pages))

    result = await engine.extract(factura)

    assert len(result.pages) == 2
    assert result.pages[0].markdown.startswith("# Página uno")
    assert result.pages[0].index == 0
    assert result.pages[1].markdown.startswith("## Página dos")
    assert result.pages[1].index == 1


async def test_paginas_incoherentes_caen_a_una_sola(factura: Path) -> None:  # C2
    # El marcador dice 2 trozos pero Azure reporta 3 páginas: no cuadra -> una sola página con todo.
    content = "trozo A<!-- PageBreak -->trozo B"
    pages = [SimpleNamespace(page_number=n, width=8.5, height=11.0) for n in (1, 2, 3)]
    engine = _engine_with_result(_fake_result(content, pages))

    result = await engine.extract(factura)

    assert len(result.pages) == 1
    assert "trozo A" in result.pages[0].markdown
    assert "trozo B" in result.pages[0].markdown


def test_sin_credenciales_no_se_construye() -> None:  # C3
    with pytest.raises(AzureDocIntelError):
        AzureDocIntelEngine(endpoint=None, key=None)

    with pytest.raises(AzureDocIntelError):
        AzureDocIntelEngine(endpoint="https://x", key="")


async def test_fichero_inexistente_da_error_tipado(tmp_path: Path) -> None:  # C4
    engine = _engine_with_result(_fake_result("x", [SimpleNamespace(page_number=1)]))

    with pytest.raises(AzureDocIntelError):
        await engine.extract(tmp_path / "no-existe.png")


async def test_fallo_del_proveedor_se_envuelve_y_encadena(factura: Path) -> None:  # C5
    client = SimpleNamespace(
        begin_analyze_document=AsyncMock(side_effect=RuntimeError("401 unauthorized"))
    )
    engine = AzureDocIntelEngine(endpoint=None, key=None, client=client)

    with pytest.raises(AzureDocIntelError) as exc_info:
        await engine.extract(factura)
    assert exc_info.value.__cause__ is not None  # encadena la excepción original


def test_registro_construye_desde_settings() -> None:  # C6
    settings = Settings(
        azure_docintel_endpoint="https://autoken-docintel-we.cognitiveservices.azure.com/",
        azure_docintel_key="test",
    )

    engine = build_docintel_engine(settings)

    assert isinstance(engine, AzureDocIntelEngine)
    assert engine.name == "azure-docintel"


def test_registro_sin_credenciales_lanza_error_tipado() -> None:  # C6
    # Forzamos vacío explícito: en local el `.env` de la raíz sí trae credenciales reales.
    settings = Settings(azure_docintel_endpoint=None, azure_docintel_key=None)

    with pytest.raises(AzureDocIntelError):
        build_docintel_engine(settings)

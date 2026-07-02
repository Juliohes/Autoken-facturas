"""Tests del motor Mistral OCR 4 (spec docs/specs/1.2-mistral-ocr4-engine.md).

El cliente de Mistral va SIEMPRE mockeado: los tests jamás llaman a la API real (sin red en CI).
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ocr.engines import (
    MistralOcr4Engine,
    MistralOcrError,
    OcrResult,
    build_default_reading_engine,
)
from shared.config import Settings


def _fake_response() -> SimpleNamespace:
    """Respuesta con la forma real de `OCRResponse` de Mistral (una página)."""
    return SimpleNamespace(
        model_dump=lambda: {
            "model": "mistral-ocr-4-0",
            "usage_info": {"pages_processed": 1},
            "pages": [
                {
                    "index": 0,
                    "markdown": "# Factura\nTotal: 121,00 EUR",
                    "dimensions": {"dpi": 200, "width": 1700, "height": 2200},
                    "blocks": [],
                }
            ],
        }
    )


def _engine_with_response(response: object) -> MistralOcr4Engine:
    client = SimpleNamespace(ocr=SimpleNamespace(process_async=AsyncMock(return_value=response)))
    return MistralOcr4Engine(api_key="test", client=client)


@pytest.fixture
def factura(tmp_path: Path) -> Path:
    ruta = tmp_path / "factura.png"
    ruta.write_bytes(b"\x89PNG bytes de prueba")
    return ruta


async def test_extract_devuelve_resultado_normalizado(factura: Path) -> None:  # C1
    engine = _engine_with_response(_fake_response())

    result = await engine.extract(factura)

    assert isinstance(result, OcrResult)
    assert result.engine == "mistral-ocr-4"
    assert result.model == "mistral-ocr-4-0"
    assert result.pages[0].markdown.startswith("# Factura")
    assert result.pages[0].width == 1700
    assert "Total" in result.text
    assert result.usage == {"pages_processed": 1}
    assert result.raw["pages"]  # el crudo del proveedor se conserva


def test_sin_api_key_no_se_construye() -> None:  # C2
    with pytest.raises(MistralOcrError):
        MistralOcr4Engine(api_key="")


async def test_fichero_inexistente_da_error_tipado(tmp_path: Path) -> None:  # C3
    engine = _engine_with_response(_fake_response())

    with pytest.raises(MistralOcrError):
        await engine.extract(tmp_path / "no-existe.png")


async def test_fallo_del_proveedor_se_envuelve_y_encadena(factura: Path) -> None:  # C4
    client = SimpleNamespace(
        ocr=SimpleNamespace(process_async=AsyncMock(side_effect=RuntimeError("401 unauthorized")))
    )
    engine = MistralOcr4Engine(api_key="test", client=client)

    with pytest.raises(MistralOcrError) as exc_info:
        await engine.extract(factura)
    assert exc_info.value.__cause__ is not None  # encadena la excepción original


@pytest.mark.parametrize(
    ("nombre", "clave"),
    [("factura.pdf", "document_url"), ("factura.jpg", "image_url"), ("factura.png", "image_url")],
)
def test_build_document_traduce_por_tipo(tmp_path: Path, nombre: str, clave: str) -> None:  # C5
    engine = _engine_with_response(_fake_response())
    ruta = tmp_path / nombre
    ruta.write_bytes(b"contenido")

    doc = engine._build_document(ruta)

    assert doc["type"] == clave
    assert doc[clave].startswith("data:")


def test_build_document_tipo_no_soportado(tmp_path: Path) -> None:  # C5
    engine = _engine_with_response(_fake_response())
    ruta = tmp_path / "factura.tiff"
    ruta.write_bytes(b"contenido")

    with pytest.raises(MistralOcrError):
        engine._build_document(ruta)


async def test_batch_extract_un_resultado_por_documento(tmp_path: Path) -> None:  # C6
    engine = _engine_with_response(_fake_response())
    a = tmp_path / "a.png"
    a.write_bytes(b"x")
    b = tmp_path / "b.png"
    b.write_bytes(b"y")

    results = await engine.batch_extract([a, b])

    assert len(results) == 2
    assert all(isinstance(r, OcrResult) for r in results)


def test_registro_entrega_mistral_como_cabeza_de_serie() -> None:  # C7
    settings = Settings(mistral_api_key="test")

    engine = build_default_reading_engine(settings)

    assert isinstance(engine, MistralOcr4Engine)
    assert engine.name == "mistral-ocr-4"

"""Tests del motor Gemini (VLM) como candidato del bench (Fase 1).

Gemini no es una API OCR nativa: es un VLM al que se le manda la imagen/PDF + un prompt de
transcripción a markdown. El cliente `google-genai` va SIEMPRE mockeado (sin red en CI). El doble
reproduce la ruta async real del SDK: `client.aio.models.generate_content(...)` -> respuesta con
`.text`, `.model_version` y `.usage_metadata`.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ocr.engines import (
    GeminiEngine,
    GeminiOcrError,
    OcrResult,
    build_gemini_engines,
)
from shared.config import Settings


def _fake_response(text: str, *, model_version: str = "gemini-3-flash") -> SimpleNamespace:
    """Respuesta con la forma real de `GenerateContentResponse` (texto + tokens)."""
    usage = SimpleNamespace(
        model_dump=lambda: {
            "prompt_token_count": 1200,
            "candidates_token_count": 300,
            "total_token_count": 1500,
        }
    )
    return SimpleNamespace(text=text, model_version=model_version, usage_metadata=usage)


def _engine_with_response(
    response: SimpleNamespace, *, name: str = "gemini-3-flash"
) -> GeminiEngine:
    gen = AsyncMock(return_value=response)
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    return GeminiEngine(
        name=name,
        model="gemini-3-flash",
        project=None,
        location="europe-west4",
        client=client,
    )


@pytest.fixture
def factura(tmp_path: Path) -> Path:
    ruta = tmp_path / "factura.png"
    ruta.write_bytes(b"\x89PNG bytes de prueba")
    return ruta


async def test_extract_devuelve_resultado_normalizado(factura: Path) -> None:  # C1
    engine = _engine_with_response(_fake_response("# Factura\nTotal: 121,00 EUR"))

    result = await engine.extract(factura)

    assert isinstance(result, OcrResult)
    assert result.engine == "gemini-3-flash"
    assert result.model == "gemini-3-flash"
    assert result.pages[0].index == 0
    assert result.pages[0].markdown.startswith("# Factura")
    assert "Total" in result.text
    assert result.usage == {
        "prompt_token_count": 1200,
        "candidates_token_count": 300,
        "total_token_count": 1500,
    }
    assert result.raw  # el crudo del proveedor se conserva


async def test_respuesta_vacia_no_cae_da_markdown_vacio(factura: Path) -> None:  # C2
    # Un VLM puede devolver texto None (p. ej. respuesta bloqueada): no debe petar, markdown vacío.
    engine = _engine_with_response(_fake_response(None))  # type: ignore[arg-type]

    result = await engine.extract(factura)

    assert result.pages[0].markdown == ""
    assert result.text == ""


def test_sin_credenciales_no_se_construye() -> None:  # C3
    with pytest.raises(GeminiOcrError):
        GeminiEngine(name="gemini-3-flash", model="gemini-3-flash", project=None, location="x")

    with pytest.raises(GeminiOcrError):
        GeminiEngine(
            name="gemini-3-flash",
            model="gemini-3-flash",
            project="autoken-ocr",
            location="x",
            credentials_path="",
        )


async def test_fichero_inexistente_da_error_tipado(tmp_path: Path) -> None:  # C4
    engine = _engine_with_response(_fake_response("x"))

    with pytest.raises(GeminiOcrError):
        await engine.extract(tmp_path / "no-existe.png")


async def test_fallo_del_proveedor_se_envuelve_y_encadena(factura: Path) -> None:  # C5
    gen = AsyncMock(side_effect=RuntimeError("403 permission denied"))
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=gen)))
    engine = GeminiEngine(
        name="gemini-3-flash", model="gemini-3-flash", project=None, location="x", client=client
    )

    with pytest.raises(GeminiOcrError) as exc_info:
        await engine.extract(factura)
    assert exc_info.value.__cause__ is not None  # encadena la excepción original


@pytest.mark.parametrize(
    ("nombre", "mime"),
    [
        ("factura.pdf", "application/pdf"),
        ("factura.jpg", "image/jpeg"),
        ("factura.png", "image/png"),
        ("factura.webp", "image/webp"),
    ],
)
def test_mime_por_tipo_de_fichero(tmp_path: Path, nombre: str, mime: str) -> None:  # C6
    engine = _engine_with_response(_fake_response("x"))
    ruta = tmp_path / nombre
    ruta.write_bytes(b"contenido")

    assert engine._mime_for(ruta) == mime


def test_tipo_no_soportado_da_error(tmp_path: Path) -> None:  # C6
    engine = _engine_with_response(_fake_response("x"))
    ruta = tmp_path / "factura.tiff"
    ruta.write_bytes(b"contenido")

    with pytest.raises(GeminiOcrError):
        engine._mime_for(ruta)


def test_r030_registro_construye_candidatos_con_ids_estables(tmp_path: Path) -> None:  # C7
    sa = tmp_path / "sa.json"
    sa.write_text("{}")
    settings = Settings(
        google_cloud_project="autoken-ocr",
        google_application_credentials=str(sa),
    )

    engines = build_gemini_engines(settings)

    names = {e.name for e in engines}
    assert names == {"gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"}
    assert all(isinstance(e, GeminiEngine) for e in engines)


def test_r030_produccion_apunta_a_flash_estable() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.gemini_flash_model == "gemini-3.5-flash"
    assert settings.gemini_35_flash_model == "gemini-3.5-flash"
    assert settings.gemini_36_flash_model == "gemini-3.6-flash"
    assert settings.gemini_35_flash_lite_model == "gemini-3.5-flash-lite"


def test_registro_sin_credenciales_lanza_error_tipado() -> None:  # C7
    settings = Settings(google_cloud_project=None, google_application_credentials=None)

    with pytest.raises(GeminiOcrError):
        build_gemini_engines(settings)

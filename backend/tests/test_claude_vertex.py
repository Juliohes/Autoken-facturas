"""Tests del adaptador Claude (Vertex) para el bench (1.2), mockeando el SDK (sin red).

Comportamiento observable: dado un fichero, el motor devuelve un `OcrResult` con el markdown
transcrito; acepta PDF nativo (bloque document); y traduce fallos del SDK a `ClaudeOcrError`.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ocr.engines.claude_vertex import ClaudeOcrError, ClaudeVertexEngine


def _fake_message(text: str) -> SimpleNamespace:
    """Respuesta de Claude: lista de bloques de contenido + model + usage."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        model="claude-sonnet-4-6",
        usage=SimpleNamespace(input_tokens=12, output_tokens=34),
    )


def _client_returning(message: Any) -> SimpleNamespace:
    return SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=message)))


def _engine(client: Any) -> ClaudeVertexEngine:
    return ClaudeVertexEngine(
        name="claude-vertex", model="claude-sonnet-4-6", project=None, location="x", client=client
    )


def _img(tmp_path: Path, name: str = "factura.png") -> Path:
    path = tmp_path / name
    path.write_bytes(b"\x89PNG bytes de prueba")
    return path


async def test_extract_devuelve_el_markdown_transcrito(tmp_path: Path) -> None:
    engine = _engine(_client_returning(_fake_message("# Factura\nA87563888 TOTAL 996,40")))
    result = await engine.extract(_img(tmp_path))
    assert result.engine == "claude-vertex"
    assert result.model == "claude-sonnet-4-6"
    assert "A87563888" in result.text
    assert result.usage == {"input_tokens": 12, "output_tokens": 34}


async def test_pdf_se_manda_como_bloque_document(tmp_path: Path) -> None:
    """Claude acepta PDF nativo: se envía como bloque `document`, no se rechaza."""
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    client = _client_returning(_fake_message("texto del pdf"))
    engine = _engine(client)
    result = await engine.extract(pdf)
    content = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert content[0]["type"] == "document"
    assert content[0]["source"]["media_type"] == "application/pdf"
    assert "texto del pdf" in result.text


async def test_imagen_se_manda_como_bloque_image(tmp_path: Path) -> None:
    client = _client_returning(_fake_message("ok"))
    engine = _engine(client)
    await engine.extract(_img(tmp_path))
    content = client.messages.create.call_args.kwargs["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert content[0]["source"]["media_type"] == "image/png"


async def test_fichero_inexistente_da_error_tipado(tmp_path: Path) -> None:
    engine = _engine(_client_returning(_fake_message("x")))
    with pytest.raises(ClaudeOcrError, match="No existe"):
        await engine.extract(tmp_path / "no-existe.png")


async def test_fallo_del_sdk_se_envuelve_y_encadena(tmp_path: Path) -> None:
    client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("429 overloaded")))
    )
    engine = _engine(client)
    with pytest.raises(ClaudeOcrError) as exc_info:
        await engine.extract(_img(tmp_path))
    assert exc_info.value.__cause__ is not None


def test_sin_credenciales_no_se_construye() -> None:
    with pytest.raises(ClaudeOcrError, match="credenciales"):
        ClaudeVertexEngine(
            name="claude-vertex", model="m", project=None, location="x", credentials_path=None
        )


def test_registro_construye_desde_settings() -> None:
    from ocr.engines.registry import build_claude_engine
    from shared.config import Settings

    settings = Settings(
        google_cloud_project="autoken-ocr",
        google_application_credentials="secrets/vertex-sa.json",
    )
    engine = build_claude_engine(settings)
    assert engine.name == "claude-vertex"

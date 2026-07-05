"""Tests del adaptador Azure OpenAI (gpt-5.1) para el bench (1.2), mockeando httpx (sin red).

Comportamiento observable: dada una imagen de factura, el motor devuelve un `OcrResult` con el
markdown transcrito; rasteriza el PDF a imagen (visión no acepta PDF nativo, #16); y traduce fallos
de la API a `AzureOpenAIError`.
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from ocr.engines.azure_openai import AzureOpenAIEngine, AzureOpenAIError
from shared.config import Settings


def _fake_response(content: str, *, status_ok: bool = True) -> SimpleNamespace:
    """Respuesta httpx falsa: raise_for_status + json() con la forma de chat/completions."""
    body = {
        "model": "gpt-5.1",
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }

    def raise_for_status() -> None:
        if not status_ok:
            raise RuntimeError("HTTP 401")

    return SimpleNamespace(raise_for_status=raise_for_status, json=lambda: body)


def _client_returning(response: Any) -> SimpleNamespace:
    return SimpleNamespace(post=AsyncMock(return_value=response))


def _engine(client: Any) -> AzureOpenAIEngine:
    return AzureOpenAIEngine("https://x.openai.azure.com", "key", "gpt-5-1", client=client)


def _img(tmp_path: Path, name: str = "factura.png") -> Path:
    path = tmp_path / name
    path.write_bytes(b"\x89PNG bytes de prueba")
    return path


async def test_extract_devuelve_el_markdown_transcrito(tmp_path: Path) -> None:
    engine = _engine(_client_returning(_fake_response("# Factura\nB56922321 TOTAL 996,40")))
    result = await engine.extract(_img(tmp_path))
    assert result.engine == "azure-openai"  # nombre por defecto
    assert result.model == "gpt-5.1"
    assert "B56922321" in result.text
    assert result.usage == {"prompt_tokens": 10, "completion_tokens": 20}


async def test_pdf_se_rasteriza_y_se_manda_como_imagen(tmp_path: Path) -> None:
    """gpt-visión no acepta PDF: se rasteriza a PNG en el paso previo y viaja como imagen (#16)."""
    pdf = tmp_path / "factura.pdf"
    Image.new("RGB", (200, 280), "white").save(pdf, "PDF")
    client = _client_returning(_fake_response("# Factura\nB56922321"))
    engine = _engine(client)

    result = await engine.extract(pdf)

    assert "B56922321" in result.text
    content = client.post.call_args.kwargs["json"]["messages"][0]["content"]
    imagenes = [part for part in content if part["type"] == "image_url"]
    assert imagenes, "el PDF debe viajar como imagen, no rechazarse"
    assert imagenes[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert imagenes[0]["image_url"]["detail"] == "high"


async def test_pdf_ilegible_da_error_tipado(tmp_path: Path) -> None:
    """Un PDF corrupto se traduce a AzureOpenAIError, no a una excepción cruda."""
    pdf = tmp_path / "roto.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    engine = _engine(_client_returning(_fake_response("x")))
    with pytest.raises(AzureOpenAIError):
        await engine.extract(pdf)


async def test_fichero_inexistente_da_error_tipado(tmp_path: Path) -> None:
    engine = _engine(_client_returning(_fake_response("x")))
    with pytest.raises(AzureOpenAIError, match="No existe"):
        await engine.extract(tmp_path / "no-existe.png")


async def test_fallo_http_se_envuelve_y_encadena(tmp_path: Path) -> None:
    engine = _engine(_client_returning(_fake_response("x", status_ok=False)))
    with pytest.raises(AzureOpenAIError) as exc_info:
        await engine.extract(_img(tmp_path))
    assert exc_info.value.__cause__ is not None


async def test_la_url_apunta_al_despliegue_y_manda_la_apikey(tmp_path: Path) -> None:
    """La llamada usa la URL REST del despliegue y la cabecera api-key (contrato de Azure)."""
    client = _client_returning(_fake_response("ok"))
    engine = AzureOpenAIEngine(
        "https://autoken-openai-sweden.openai.azure.com/",
        "secreta",
        "gpt-5-1",
        api_version="2024-12-01-preview",
        client=client,
    )
    await engine.extract(_img(tmp_path))
    url = client.post.call_args.args[0]
    headers = client.post.call_args.kwargs["headers"]
    payload = client.post.call_args.kwargs["json"]
    assert "/openai/deployments/gpt-5-1/chat/completions" in url
    assert "api-version=2024-12-01-preview" in url
    assert headers["api-key"] == "secreta"
    # gpt-5.1 es de razonamiento: max_completion_tokens y sin temperature.
    assert "max_completion_tokens" in payload
    assert "temperature" not in payload
    # Esfuerzo de razonamiento bajo: para OCR no aporta y truncaba la salida (se perdía el CIF).
    assert payload["reasoning_effort"] == "low"
    # La imagen se manda en alta resolución para no perder el texto pequeño (CIF).
    image = payload["messages"][0]["content"][1]["image_url"]
    assert image["detail"] == "high"


def test_sin_config_no_se_construye() -> None:
    with pytest.raises(AzureOpenAIError, match="sin configurar"):
        AzureOpenAIEngine(None, None, None)


def test_registro_construye_desde_settings_con_nombre_gpt() -> None:
    from ocr.engines.registry import build_azure_openai_engine

    settings = Settings(
        azure_openai_endpoint="https://x.openai.azure.com",
        azure_openai_key="k",
        azure_openai_deployment="gpt-5-1",
    )
    engine = build_azure_openai_engine(settings)
    assert engine.name == "gpt-5.1"


def test_registro_sin_config_lanza_error_tipado() -> None:
    from ocr.engines.registry import build_azure_openai_engine

    # `_env_file=None`: ignora el `.env` real (que sí trae las claves) para probar el caso vacío.
    with pytest.raises(AzureOpenAIError):
        build_azure_openai_engine(Settings(_env_file=None))  # type: ignore[call-arg]

"""Tests del adaptador de Azure OpenAI y de las utilidades comunes de motores (tarea 1.2).

No tocan red ni servicios de pago: el cliente httpx se inyecta con un MockTransport que
devuelve respuestas canónicas. Cubren el parseo robusto del JSON del modelo, la regla
anti-alucinación (null → None), el cálculo de coste/latencia, la forma de la petición
(despliegue en la ruta, cabecera api-key, response_format JSON) y el camino de error.
"""

from __future__ import annotations

import base64
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from ocr.bench.engines.azure_openai import AzureOpenAIConfig, AzureOpenAIEngine
from ocr.bench.engines.base import EngineError, encode_image, parse_invoice_json

# --- 1x1 PNG transparente, suficiente para ejercitar encode_image sin binarios externos ----
_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


@pytest.fixture
def invoice_png(tmp_path: Path) -> Path:
    path = tmp_path / "factura.png"
    path.write_bytes(_PNG_1X1)
    return path


def _config() -> AzureOpenAIConfig:
    return AzureOpenAIConfig(
        endpoint="https://autoken-openai-sweden.openai.azure.com/",
        api_key="test-key",
        deployment="autoken-gpt-41",
        api_version="2024-10-21",
        eur_per_1k_input=Decimal("0.002"),
        eur_per_1k_output=Decimal("0.008"),
    )


def _completion(content: str, *, prompt_tokens: int = 1000, completion_tokens: int = 100) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
    }


# --- parse_invoice_json ---------------------------------------------------------------------


def test_parse_invoice_json_full() -> None:
    fields = parse_invoice_json(
        json.dumps(
            {
                "numero": "FRA-2026-001",
                "fecha": "2026-03-14",
                "emisor_nombre": "Acme S.L.",
                "emisor_nif": "B12345678",
                "receptor_nombre": "Setex",
                "receptor_nif": "B87654321",
                "tramos": [{"base": "100.00", "iva_pct": "21", "cuota": "21.00"}],
                "irpf_cuota": "0",
                "total": "121.00",
            }
        )
    )
    assert fields.numero == "FRA-2026-001"
    assert fields.receptor_nif == "B87654321"
    assert fields.total == Decimal("121.00")
    assert len(fields.tramos) == 1
    assert fields.tramos[0].cuota == Decimal("21.00")


def test_parse_invoice_json_strips_code_fences() -> None:
    fields = parse_invoice_json('```json\n{"numero": "X-1", "total": 50}\n```')
    assert fields.numero == "X-1"
    assert fields.total == Decimal("50")


def test_parse_invoice_json_null_is_none_not_invented() -> None:
    fields = parse_invoice_json('{"numero": null, "receptor_nif": "", "total": null}')
    assert fields.numero is None
    assert fields.receptor_nif is None  # cadena vacía también es ausencia
    assert fields.total is None


def test_parse_invoice_json_drops_incomplete_tramo() -> None:
    fields = parse_invoice_json('{"tramos": [{"base": "100", "iva_pct": "21"}]}')
    assert fields.tramos == ()  # tramo sin cuota se descarta, no se inventa


def test_parse_invoice_json_rejects_non_object() -> None:
    with pytest.raises(EngineError):
        parse_invoice_json("[1, 2, 3]")


def test_parse_invoice_json_rejects_bad_number() -> None:
    with pytest.raises(EngineError):
        parse_invoice_json('{"total": "no-soy-un-numero"}')


# --- encode_image ---------------------------------------------------------------------------


def test_encode_image_png(invoice_png: Path) -> None:
    b64, mime = encode_image(invoice_png)
    assert mime == "image/png"
    assert base64.b64decode(b64) == _PNG_1X1


def test_encode_image_pdf_rejected(tmp_path: Path) -> None:
    pdf = tmp_path / "factura.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    with pytest.raises(EngineError, match="rasterizado"):
        encode_image(pdf)


# --- AzureOpenAIEngine ----------------------------------------------------------------------


def test_engine_requires_configuration() -> None:
    empty = AzureOpenAIConfig(endpoint="", api_key="", deployment="")
    assert empty.is_configured is False
    with pytest.raises(EngineError, match="sin configurar"):
        AzureOpenAIEngine(empty)


def test_engine_extract_success(invoice_png: Path) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("api-key")
        captured["body"] = json.loads(request.content)
        content = json.dumps(
            {"numero": "FRA-1", "fecha": "2026-01-02", "receptor_nif": "B87654321", "total": "121"}
        )
        return httpx.Response(200, json=_completion(content))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    engine = AzureOpenAIEngine(_config(), client=client)

    result = engine.extract(invoice_png)

    assert result.error is None
    assert result.engine == "azure-openai"
    assert result.fields.numero == "FRA-1"
    assert result.fields.receptor_nif == "B87654321"
    assert result.fields.total == Decimal("121")
    # Coste real desde usage: 1000/1000*0.002 + 100/1000*0.008 = 0.002 + 0.0008
    assert result.cost_eur == Decimal("0.0028")
    assert result.duration_ms >= 0
    # La petición usa el nombre del despliegue en la ruta y la cabecera api-key.
    assert "deployments/autoken-gpt-41/chat/completions" in str(captured["url"])
    assert "api-version=2024-10-21" in str(captured["url"])
    assert captured["api_key"] == "test-key"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0


def test_engine_extract_http_error_is_wrapped(invoice_png: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limit"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    engine = AzureOpenAIEngine(_config(), client=client)

    result = engine.extract(invoice_png)

    assert result.error is not None
    assert "429" in result.error or "Client error" in result.error
    assert result.fields.numero is None  # sin datos inventados ante el fallo


def test_engine_extract_bad_json_from_model_is_wrapped(invoice_png: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_completion("esto no es json"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    engine = AzureOpenAIEngine(_config(), client=client)

    result = engine.extract(invoice_png)

    assert result.error is not None
    assert result.fields == result.fields.__class__()  # InvoiceFields vacío


def test_chat_completions_url_shape() -> None:
    url = _config().chat_completions_url()
    assert url == (
        "https://autoken-openai-sweden.openai.azure.com/openai/deployments/"
        "autoken-gpt-41/chat/completions?api-version=2024-10-21"
    )

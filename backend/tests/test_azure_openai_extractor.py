"""Tests del extractor estructurado de gpt-5.1 para el ranking multi-modelo (S4.8).

Mockea httpx (sin red, sin coste). Comportamiento observable: dada una respuesta JSON del modelo,
devuelve un `ExtractedInvoice`; el PDF se rasteriza antes de mandarse (gpt-visión no acepta PDF).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from ocr.engines.azure_openai_extractor import AzureOpenAIInvoiceExtractor
from ocr.extraction import InvoiceExtractionError

_VALID_PAYLOAD = {
    "issue_date": "2026-05-10",
    "issue_date_confidence": "alta",
    "total_amount": 121.0,
    "total_confidence": "alta",
    "net_amount": 100.0,
    "tax_amount": 21.0,
    "tax_lines": [{"base": 100.0, "rate": 21.0, "cuota": 21.0}],
    "tax_ids": [{"value": "A39031620", "name": "Proveedor SA", "confidence": "alta"}],
}


def _fake_response(content: str, *, status_ok: bool = True) -> SimpleNamespace:
    body = {"model": "gpt-5.1", "choices": [{"message": {"content": content}}]}

    def raise_for_status() -> None:
        if not status_ok:
            raise RuntimeError("HTTP 401")

    return SimpleNamespace(raise_for_status=raise_for_status, json=lambda: body)


def _client_returning(response: Any) -> SimpleNamespace:
    return SimpleNamespace(post=AsyncMock(return_value=response))


def _extractor(client: Any) -> AzureOpenAIInvoiceExtractor:
    return AzureOpenAIInvoiceExtractor(
        "https://x.openai.azure.com",
        "key",
        "gpt-5-1",
        api_version="2024-12-01-preview",
        client=client,
    )


def _png_bytes() -> bytes:
    import io

    buffer = io.BytesIO()
    Image.new("RGB", (100, 60), "white").save(buffer, format="PNG")
    return buffer.getvalue()


async def test_extrae_los_campos_de_la_respuesta_json() -> None:
    client = _client_returning(_fake_response(json.dumps(_VALID_PAYLOAD)))
    extractor = _extractor(client)

    invoice = await extractor.extract(_png_bytes(), "image/png")

    assert invoice.engine == "gpt-5.1"
    assert invoice.tax_ids[0].value == "A39031620"


async def test_pdf_se_rasteriza_antes_de_mandarse() -> None:
    """gpt-visión no acepta PDF: se rasteriza a PNG en memoria (S4.8, sin fichero en disco)."""
    import io

    pdf_buffer = io.BytesIO()
    Image.new("RGB", (200, 280), "white").save(pdf_buffer, "PDF")

    client = _client_returning(_fake_response(json.dumps(_VALID_PAYLOAD)))
    extractor = _extractor(client)

    await extractor.extract(pdf_buffer.getvalue(), "application/pdf")

    content = client.post.call_args.kwargs["json"]["messages"][0]["content"]
    imagenes = [part for part in content if part["type"] == "image_url"]
    assert imagenes, "el PDF debe viajar como imagen, no rechazarse"
    assert imagenes[0]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_content_type_no_soportado_da_error_tipado() -> None:
    extractor = _extractor(_client_returning(_fake_response("{}")))
    with pytest.raises(InvoiceExtractionError, match="no soportado"):
        await extractor.extract(b"x", "application/zip")


async def test_fallo_http_se_envuelve_y_encadena() -> None:
    extractor = _extractor(_client_returning(_fake_response("x", status_ok=False)))
    with pytest.raises(InvoiceExtractionError) as exc_info:
        await extractor.extract(_png_bytes(), "image/png")
    assert exc_info.value.__cause__ is not None


def test_sin_config_no_se_construye() -> None:
    with pytest.raises(InvoiceExtractionError, match="sin configurar"):
        AzureOpenAIInvoiceExtractor(None, None, None, api_version="2024-12-01-preview")


def test_build_azure_openai_extractor_usa_la_config() -> None:
    from ocr.engines.azure_openai_extractor import build_azure_openai_extractor
    from shared.config import Settings

    with pytest.raises(InvoiceExtractionError):
        build_azure_openai_extractor(Settings(_env_file=None))  # type: ignore[call-arg]

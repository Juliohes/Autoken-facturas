"""Tests del extractor estructurado de Claude para el ranking multi-modelo (S4.8).

Mockea `AsyncAnthropicVertex` (sin red, sin coste). Comportamiento observable: dada una respuesta
JSON del modelo, devuelve un `ExtractedInvoice`; fallo del SDK o JSON inválido -> error tipado.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ocr.engines.claude_extractor import ClaudeInvoiceExtractor
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


def _fake_message(text: str, *, model: str = "claude-sonnet-4-5") -> SimpleNamespace:
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(content=[block], model=model)


def _client_returning(message: Any) -> SimpleNamespace:
    return SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(return_value=message)))


def _extractor(client: Any) -> ClaudeInvoiceExtractor:
    return ClaudeInvoiceExtractor(
        model="claude-sonnet-4-5",
        project="autoken-ocr",
        location="global",
        credentials_path="/secrets/vertex-sa.json",
        client=client,
    )


async def test_extrae_los_campos_de_la_respuesta_json() -> None:
    client = _client_returning(_fake_message(json.dumps(_VALID_PAYLOAD)))
    extractor = _extractor(client)

    invoice = await extractor.extract(b"bytes de la imagen", "image/jpeg")

    assert invoice.engine == "claude-vertex"
    assert invoice.tax_ids[0].value == "A39031620"
    assert invoice.total_amount is not None


async def test_pdf_se_manda_como_bloque_document_no_imagen() -> None:
    """Claude acepta PDF nativo (bloque `document`), a diferencia de gpt-visión (#16)."""
    client = _client_returning(_fake_message(json.dumps(_VALID_PAYLOAD)))
    extractor = _extractor(client)

    await extractor.extract(b"%PDF-1.4 bytes", "application/pdf")

    messages = client.messages.create.call_args.kwargs["messages"]
    blocks = messages[0]["content"]
    document_blocks = [b for b in blocks if b["type"] == "document"]
    assert document_blocks, "un PDF debe viajar como bloque document, no como imagen"
    assert document_blocks[0]["source"]["media_type"] == "application/pdf"


async def test_content_type_no_soportado_da_error_tipado() -> None:
    extractor = _extractor(_client_returning(_fake_message("{}")))
    with pytest.raises(InvoiceExtractionError, match="no soportado"):
        await extractor.extract(b"x", "application/zip")


async def test_fallo_del_sdk_se_envuelve_y_encadena() -> None:
    client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(side_effect=RuntimeError("503")))
    )
    extractor = _extractor(client)
    with pytest.raises(InvoiceExtractionError) as exc_info:
        await extractor.extract(b"x", "image/png")
    assert exc_info.value.__cause__ is not None


def test_sin_credenciales_no_se_construye() -> None:
    with pytest.raises(InvoiceExtractionError, match="Faltan las credenciales"):
        ClaudeInvoiceExtractor(
            model="claude-sonnet-4-5", project=None, location="global", credentials_path=None
        )


def test_build_claude_extractor_usa_la_config() -> None:
    from ocr.engines.claude_extractor import build_claude_extractor
    from shared.config import Settings

    with pytest.raises(InvoiceExtractionError):
        # `_env_file=None`: ignora el `.env` real para probar el caso sin credenciales.
        build_claude_extractor(Settings(_env_file=None))  # type: ignore[call-arg]

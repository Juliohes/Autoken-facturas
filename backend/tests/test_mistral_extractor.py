"""Tests del extractor de Mistral OCR 4 para el ranking multi-modelo (R-029)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ocr.engines.mistral_extractor import MistralInvoiceExtractor
from ocr.extraction import InvoiceExtractionError


def _fake_response() -> SimpleNamespace:
    return SimpleNamespace(
        model="mistral-ocr-4-0",
        document_annotation='{"issue_date":"2026-01-31","total_amount":"121.00",'
        '"net_amount":"100.00","tax_amount":"21.00","invoice_number":"F-1",'
        '"tax_lines":[{"rate":"21","base":"100.00","quota":"21.00"}],'
        '"tax_ids":[{"value":"B12345678","name":"Proveedor SA"}]}',
        model_dump=lambda: {
            "model": "mistral-ocr-4-0",
            "document_annotation": "structured",
            "pages": [{"markdown": "texto libre"}],
        },
    )


def _client_returning(response: Any) -> SimpleNamespace:
    return SimpleNamespace(ocr=SimpleNamespace(process_async=AsyncMock(return_value=response)))


def _extractor(client: Any) -> MistralInvoiceExtractor:
    return MistralInvoiceExtractor("api-key", model="mistral-ocr-4-0", client=client)


async def test_r029_mistral_devuelve_campos_estructurados_y_amounts_decimal() -> None:
    client = _client_returning(_fake_response())
    extractor = _extractor(client)

    invoice = await extractor.extract(b"bytes de la imagen", "image/jpeg")

    assert invoice.engine == "mistral-ocr-4"
    assert str(invoice.issue_date) == "2026-01-31"
    assert str(invoice.total_amount) == "121.00"
    assert str(invoice.net_amount) == "100.00"
    assert str(invoice.tax_amount) == "21.00"
    assert str(invoice.tax_lines[0].cuota) == "21.00"
    assert invoice.tax_ids[0].value == "B12345678"
    assert invoice.issue_date_confidence == "baja"
    assert invoice.total_confidence == "baja"
    assert invoice.invoice_number == "F-1"
    assert invoice.invoice_number_confidence == "baja"
    assert invoice.net_amount_confidence == "baja"
    assert invoice.tax_amount_confidence == "baja"
    call = client.ocr.process_async.call_args.kwargs
    assert call["confidence_scores_granularity"] == "page"
    assert call["document_annotation_format"]["type"] == "json_schema"
    assert call["document_annotation_format"]["json_schema"]["name"] == "invoice_extraction"
    assert call["document_annotation_prompt"]


async def test_r029_sin_anotacion_estructurada_da_error() -> None:
    response = SimpleNamespace(
        model="mistral-ocr-4-0",
        document_annotation=None,
        model_dump=lambda: {},
    )
    extractor = _extractor(_client_returning(response))

    with pytest.raises(InvoiceExtractionError, match="document_annotation"):
        await extractor.extract(b"bytes", "image/jpeg")


async def test_content_type_no_soportado_da_error_tipado() -> None:
    extractor = _extractor(_client_returning(_fake_response()))
    with pytest.raises(InvoiceExtractionError, match="no soportado"):
        await extractor.extract(b"x", "application/zip")


async def test_fallo_de_la_api_se_envuelve_y_encadena() -> None:
    client = SimpleNamespace(
        ocr=SimpleNamespace(process_async=AsyncMock(side_effect=RuntimeError("timeout")))
    )
    extractor = _extractor(client)
    with pytest.raises(InvoiceExtractionError) as exc_info:
        await extractor.extract(b"x", "image/png")
    assert exc_info.value.__cause__ is not None


def test_sin_api_key_no_se_construye() -> None:
    with pytest.raises(InvoiceExtractionError, match="Falta la API key"):
        MistralInvoiceExtractor(None, model="mistral-ocr-4-0")


def test_build_mistral_extractor_usa_la_config() -> None:
    from ocr.engines.mistral_extractor import build_mistral_extractor
    from shared.config import Settings

    with pytest.raises(InvoiceExtractionError):
        build_mistral_extractor(Settings(_env_file=None))  # type: ignore[call-arg]

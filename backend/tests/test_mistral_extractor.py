"""Tests del extractor de Mistral OCR 4 para el ranking multi-modelo (S4.8).

Mockea el cliente Mistral (sin red, sin coste). Criterio C5 de la spec: Mistral es una API de OCR
puro sin campos estructurados — pase lo que pase, la lectura siempre tiene todos los campos `None`.
"""

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
        model_dump=lambda: {"pages": [{"markdown": "texto libre, sin campos"}]},
    )


def _client_returning(response: Any) -> SimpleNamespace:
    return SimpleNamespace(ocr=SimpleNamespace(process_async=AsyncMock(return_value=response)))


def _extractor(client: Any) -> MistralInvoiceExtractor:
    return MistralInvoiceExtractor("api-key", model="mistral-ocr-4-0", client=client)


async def test_c5_todos_los_campos_quedan_null_pase_lo_que_pase() -> None:
    """C5: Mistral no tiene forma de dar campos estructurados; nunca se inventan."""
    extractor = _extractor(_client_returning(_fake_response()))

    invoice = await extractor.extract(b"bytes de la imagen", "image/jpeg")

    assert invoice.engine == "mistral-ocr-4"
    assert invoice.issue_date is None
    assert invoice.total_amount is None
    assert invoice.net_amount is None
    assert invoice.tax_amount is None
    assert invoice.tax_lines == ()
    assert invoice.tax_ids == ()
    assert invoice.issue_date_confidence == "baja"
    assert invoice.total_confidence == "baja"
    assert invoice.invoice_number is None  # spec: S6.1 C4 (asimetría de Mistral, sin inventar)
    assert invoice.invoice_number_confidence == "baja"
    assert invoice.net_amount_confidence == "baja"  # spec: S6.1 C28
    assert invoice.tax_amount_confidence == "baja"


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

"""Tests del parseo JSON->ExtractedInvoice compartido (S4.8, extraído de gemini_extractor S2.3).

Módulo puro: sin red, sin SDK. Reutilizado por los 4 extractores "promptables" del ranking
multi-modelo (Gemini Flash/Pro, Claude, gpt-5.1); se prueba una sola vez aquí.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from ocr.extraction import InvoiceExtractionError
from ocr.extraction_json import parse_structured_invoice

_VALID_PAYLOAD = {
    "issue_date": "2026-05-10",
    "issue_date_confidence": "alta",
    "total_amount": 121.0,
    "total_confidence": "alta",
    "net_amount": 100.0,
    "tax_amount": 21.0,
    "tax_lines": [{"base": 100.0, "rate": 21.0, "cuota": 21.0}],
    "tax_ids": [{"value": "B06183446", "name": "Mi Empresa SL", "confidence": "alta"}],
}


def test_parsea_un_json_valido_a_extracted_invoice() -> None:
    invoice = parse_structured_invoice(
        json.dumps(_VALID_PAYLOAD), engine="claude-vertex", model="claude-x"
    )
    assert invoice.engine == "claude-vertex"
    assert invoice.model == "claude-x"
    assert invoice.total_amount == Decimal("121.0")
    assert invoice.tax_ids[0].value == "B06183446"
    assert invoice.tax_lines[0].cuota == Decimal("21.0")


def test_campo_no_legible_queda_null_no_inventado() -> None:
    payload = dict(_VALID_PAYLOAD, total_amount=None, tax_ids=[])
    invoice = parse_structured_invoice(json.dumps(payload), engine="gpt-5.1", model="gpt-5.1")
    assert invoice.total_amount is None
    assert invoice.tax_ids == ()


def test_respuesta_vacia_da_error_tipado() -> None:
    with pytest.raises(InvoiceExtractionError, match="respuesta vacía"):
        parse_structured_invoice(None, engine="gemini-3-pro", model="x")
    with pytest.raises(InvoiceExtractionError, match="respuesta vacía"):
        parse_structured_invoice("", engine="gemini-3-pro", model="x")


def test_json_invalido_da_error_tipado() -> None:
    with pytest.raises(InvoiceExtractionError, match="no es JSON válido"):
        parse_structured_invoice("esto no es json", engine="claude-vertex", model="x")


def test_confianza_desconocida_cae_a_baja() -> None:
    payload = dict(_VALID_PAYLOAD, total_confidence="segura")
    invoice = parse_structured_invoice(json.dumps(payload), engine="gpt-5.1", model="x")
    assert invoice.total_confidence == "baja"


def test_contenido_no_coercible_da_error_tipado() -> None:
    payload = dict(_VALID_PAYLOAD, total_amount="no-es-un-numero")
    with pytest.raises(InvoiceExtractionError, match="No se pudo interpretar"):
        parse_structured_invoice(json.dumps(payload), engine="claude-vertex", model="x")

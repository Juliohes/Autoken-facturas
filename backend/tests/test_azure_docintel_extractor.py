"""Tests del extractor estructurado de Azure Document Intelligence (`prebuilt-invoice`, S4.8).

El cliente va SIEMPRE mockeado (sin red en CI). El doble reproduce la forma del SDK v1:
`begin_analyze_document` async devuelve un poller cuyo `.result()` async entrega un `AnalyzeResult`
con `documents[0].fields` — un dict de campos con `.value_string`/`.value_date`/`.value_currency`/
`.confidence`, la forma documentada del modelo `prebuilt-invoice`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ocr.engines.azure_docintel_extractor import AzureDocIntelInvoiceExtractor
from ocr.extraction import InvoiceExtractionError


def _field(*, value_string=None, value_date=None, value_currency=None, confidence=None):
    return SimpleNamespace(
        value_string=value_string,
        value_date=value_date,
        value_currency=value_currency,
        confidence=confidence,
        content=value_string,
    )


def _currency(amount: float) -> SimpleNamespace:
    return SimpleNamespace(amount=amount)


def _fake_result(fields: dict[str, Any], *, model_id: str = "prebuilt-invoice") -> SimpleNamespace:
    document = SimpleNamespace(fields=fields)
    return SimpleNamespace(documents=[document], model_id=model_id)


def _extractor_with_result(result: SimpleNamespace) -> AzureDocIntelInvoiceExtractor:
    poller = SimpleNamespace(result=AsyncMock(return_value=result))
    client = SimpleNamespace(begin_analyze_document=AsyncMock(return_value=poller))
    return AzureDocIntelInvoiceExtractor(endpoint=None, key=None, client=client)


async def test_c6_traduce_los_campos_reconocidos() -> None:
    """C6: campos de Azure (VendorTaxId/InvoiceDate/InvoiceTotal...) -> ExtractedInvoice."""
    fields = {
        "VendorTaxId": _field(value_string="A39031620", confidence=0.95),
        "VendorName": _field(value_string="Proveedor SA", confidence=0.95),
        "CustomerTaxId": _field(value_string="B06183446", confidence=0.9),
        "CustomerName": _field(value_string="Mi Empresa SL", confidence=0.9),
        "InvoiceDate": _field(value_date=date(2026, 5, 10), confidence=0.98),
        "InvoiceTotal": _field(value_currency=_currency(121.0), confidence=0.97),
        "SubTotal": _field(value_currency=_currency(100.0), confidence=0.9),
        "TotalTax": _field(value_currency=_currency(21.0), confidence=0.9),
    }
    extractor = _extractor_with_result(_fake_result(fields))

    invoice = await extractor.extract(b"bytes de la imagen", "image/jpeg")

    assert invoice.engine == "azure-docintel"
    assert invoice.issue_date == date(2026, 5, 10)
    assert invoice.total_amount == Decimal("121.0")
    assert invoice.net_amount == Decimal("100.0")
    assert invoice.tax_amount == Decimal("21.0")
    values = {tid.value for tid in invoice.tax_ids}
    assert values == {"A39031620", "B06183446"}
    assert invoice.tax_lines == ()  # Azure no da desglose de IVA por tipo (ver docstring)


async def test_s6_14_azure_usa_la_misma_confianza_para_valor_y_nombre() -> None:
    """S6.14: Azure no distingue confianza de valor vs de nombre (limitación conocida del motor,
    ver docstring de `_tax_id`) -- ambos campos deben llevar la MISMA confianza calculada."""
    fields = {
        "VendorTaxId": _field(value_string="A39031620", confidence=0.95),
        "VendorName": _field(value_string="Proveedor SA", confidence=0.95),
    }
    extractor = _extractor_with_result(_fake_result(fields))

    invoice = await extractor.extract(b"x", "image/png")

    assert len(invoice.tax_ids) == 1
    tax_id = invoice.tax_ids[0]
    assert tax_id.value_confidence == "alta"
    assert tax_id.name_confidence == "alta"


async def test_s6_1_c1_traduce_el_numero_de_factura() -> None:
    """spec: S6.1 C1 — `InvoiceId` de Azure (`prebuilt-invoice`) -> `invoice_number` + confianza."""
    fields = {"InvoiceId": _field(value_string="F-2026-001", confidence=0.95)}
    extractor = _extractor_with_result(_fake_result(fields))

    invoice = await extractor.extract(b"x", "image/png")

    assert invoice.invoice_number == "F-2026-001"
    assert invoice.invoice_number_confidence == "alta"


async def test_s6_1_c25_traduce_la_confianza_de_base_imponible_e_iva() -> None:
    """spec: S6.1 C25 — `SubTotal`/`TotalTax` de Azure también aportan su propia confianza, no
    solo el importe (Área F, ampliación)."""
    fields = {
        "SubTotal": _field(value_currency=_currency(100.0), confidence=0.95),
        "TotalTax": _field(value_currency=_currency(21.0), confidence=0.4),
    }
    extractor = _extractor_with_result(_fake_result(fields))

    invoice = await extractor.extract(b"x", "image/png")

    assert invoice.net_amount_confidence == "alta"
    assert invoice.tax_amount_confidence == "baja"


async def test_c6_campo_no_reconocido_por_azure_queda_null() -> None:
    """Anti-alucinación: un campo que Azure no reconoció en la factura nunca se inventa."""
    extractor = _extractor_with_result(_fake_result({}))

    invoice = await extractor.extract(b"x", "image/png")

    assert invoice.issue_date is None
    assert invoice.total_amount is None
    assert invoice.tax_ids == ()
    assert invoice.invoice_number is None  # spec: S6.1 C2


@pytest.mark.parametrize(("score", "expected"), [(0.95, "alta"), (0.7, "media"), (0.2, "baja")])
async def test_confianza_de_azure_se_normaliza(score: float, expected: str) -> None:
    fields = {"InvoiceTotal": _field(value_currency=_currency(121.0), confidence=score)}
    extractor = _extractor_with_result(_fake_result(fields))

    invoice = await extractor.extract(b"x", "image/png")

    assert invoice.total_confidence == expected


async def test_content_type_no_soportado_da_error_tipado() -> None:
    extractor = _extractor_with_result(_fake_result({}))
    with pytest.raises(InvoiceExtractionError, match="no soportado"):
        await extractor.extract(b"x", "application/zip")


async def test_fallo_del_proveedor_se_envuelve_y_encadena() -> None:
    client = SimpleNamespace(
        begin_analyze_document=AsyncMock(side_effect=RuntimeError("401 unauthorized"))
    )
    extractor = AzureDocIntelInvoiceExtractor(endpoint=None, key=None, client=client)
    with pytest.raises(InvoiceExtractionError) as exc_info:
        await extractor.extract(b"x", "image/png")
    assert exc_info.value.__cause__ is not None


def test_sin_credenciales_no_se_construye() -> None:
    with pytest.raises(InvoiceExtractionError, match="Faltan las credenciales"):
        AzureDocIntelInvoiceExtractor(endpoint=None, key=None)


def test_build_azure_docintel_extractor_usa_la_config() -> None:
    from ocr.engines.azure_docintel_extractor import build_azure_docintel_extractor
    from shared.config import Settings

    with pytest.raises(InvoiceExtractionError):
        build_azure_docintel_extractor(Settings(_env_file=None))  # type: ignore[call-arg]

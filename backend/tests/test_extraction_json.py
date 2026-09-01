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
    "net_amount_confidence": "alta",
    "tax_amount": 21.0,
    "tax_amount_confidence": "alta",
    "irpf_rate": 19.0,
    "irpf_rate_confidence": "alta",
    "irpf_amount": 19.0,
    "irpf_amount_confidence": "alta",
    "invoice_number": "F-2026-001",
    "invoice_number_confidence": "alta",
    "tax_lines": [{"base": 100.0, "rate": 21.0, "cuota": 21.0}],
    "tax_ids": [
        {
            "value": "B06183446",
            "name": "Mi Empresa SL",
            "value_confidence": "alta",
            "name_confidence": "alta",
        }
    ],
}

_COMMON_PAYLOAD = {
    "schema_version": "1",
    "issue_date": "2026-05-10",
    "invoice_number": "F-2026-001",
    "total_amount": "121.00",
    "net_amount": "100.00",
    "tax_amount": "21.00",
    "irpf_rate": "19.00",
    "irpf_amount": "19.00",
    "tax_lines": [{"base": "100.00", "rate": "21", "quota": "21.00"}],
    "tax_ids": [{"value": "B06183446", "name": "Mi Empresa SL"}],
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
    assert invoice.irpf_rate == Decimal("19.0")
    assert invoice.irpf_amount == Decimal("19.0")


def test_r031_parsea_el_contrato_comun_con_amounts_string() -> None:
    invoice = parse_structured_invoice(
        json.dumps(_COMMON_PAYLOAD), engine="gemini-3.5-flash", model="gemini-3.5-flash"
    )

    assert invoice.total_amount == Decimal("121.00")
    assert invoice.tax_lines[0].base == Decimal("100.00")
    assert invoice.tax_lines[0].cuota == Decimal("21.00")
    assert invoice.total_confidence == "baja"
    assert invoice.raw["schema_version"] == "1"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("450,00", Decimal("450.00")),
        ("1.234,56", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
    ],
)
def test_r031_parsea_importes_con_formato_espanol_o_ingles(
    value: str, expected: Decimal
) -> None:
    payload = dict(
        _COMMON_PAYLOAD,
        total_amount=value,
        tax_lines=[{"base": value, "rate": "21", "quota": "94,50"}],
    )

    invoice = parse_structured_invoice(
        json.dumps(payload), engine="gemini-3.5-flash", model="gemini-3.5-flash"
    )

    assert invoice.total_amount == expected
    assert invoice.tax_lines[0].base == expected
    assert invoice.tax_lines[0].cuota == Decimal("94.50")


def test_r031_rechaza_una_version_de_schema_desconocida() -> None:
    payload = dict(_COMMON_PAYLOAD, schema_version="2")

    with pytest.raises(InvoiceExtractionError, match="Versión de schema no soportada"):
        parse_structured_invoice(json.dumps(payload), engine="claude-vertex", model="x")


def test_r031_rechaza_importes_numericos_en_el_contrato_comun() -> None:
    payload = dict(_COMMON_PAYLOAD, total_amount=121.0)

    with pytest.raises(InvoiceExtractionError, match="contrato común"):
        parse_structured_invoice(json.dumps(payload), engine="gpt-5.1", model="x")


def test_s6_14_c4_parsea_confianza_del_valor_y_del_nombre_por_separado() -> None:
    """spec: S6.14 C4 — `value_confidence`/`name_confidence` de cada `tax_id`, no una combinada."""
    payload = dict(
        _VALID_PAYLOAD,
        tax_ids=[
            {
                "value": "A39031620",
                "name": "Comercial del logo SL",
                "value_confidence": "alta",
                "name_confidence": "baja",
            }
        ],
    )
    invoice = parse_structured_invoice(json.dumps(payload), engine="claude-vertex", model="x")
    assert invoice.tax_ids[0].value_confidence == "alta"
    assert invoice.tax_ids[0].name_confidence == "baja"


def test_s6_14_c4_confianza_de_nombre_desconocida_cae_a_baja() -> None:
    """Igual que `total_confidence`: una etiqueta no reconocida en `name_confidence` -> "baja"."""
    payload = dict(
        _VALID_PAYLOAD,
        tax_ids=[
            {
                "value": "A39031620",
                "name": "Proveedor SA",
                "value_confidence": "alta",
                "name_confidence": "segura",
            }
        ],
    )
    invoice = parse_structured_invoice(json.dumps(payload), engine="gpt-5.1", model="x")
    assert invoice.tax_ids[0].name_confidence == "baja"


def test_s6_14_c5_el_prompt_indica_priorizar_la_razon_social_legal() -> None:
    """spec: S6.14 C5 — el prompt debe distinguir razón social legal de nombre comercial."""
    from ocr.extraction_json import EXTRACTION_PROMPT

    assert "razón social" in EXTRACTION_PROMPT.lower()
    assert "value_confidence" in EXTRACTION_PROMPT
    assert "name_confidence" in EXTRACTION_PROMPT


def test_campo_no_legible_queda_null_no_inventado() -> None:
    payload = dict(_VALID_PAYLOAD, total_amount=None, tax_ids=[])
    invoice = parse_structured_invoice(json.dumps(payload), engine="gpt-5.1", model="gpt-5.1")
    assert invoice.total_amount is None
    assert invoice.tax_ids == ()


def test_s6_1_c1_parsea_numero_de_factura_y_su_confianza() -> None:
    """spec: S6.1 C1 — `invoice_number`/`invoice_number_confidence` del JSON compartido."""
    invoice = parse_structured_invoice(
        json.dumps(_VALID_PAYLOAD), engine="gemini-3-flash", model="gemini-3-flash"
    )
    assert invoice.invoice_number == "F-2026-001"
    assert invoice.invoice_number_confidence == "alta"


def test_s6_1_c2_numero_de_factura_no_legible_queda_null() -> None:
    """spec: S6.1 C2 (anti-alucinación) — `invoice_number: null` en el JSON -> `None`."""
    payload = dict(_VALID_PAYLOAD, invoice_number=None)
    invoice = parse_structured_invoice(json.dumps(payload), engine="claude-vertex", model="x")
    assert invoice.invoice_number is None


def test_s6_1_c25_parsea_confianza_propia_de_base_imponible_e_iva() -> None:
    """spec: S6.1 C25 — `net_amount_confidence`/`tax_amount_confidence` (Área F, ampliación)."""
    invoice = parse_structured_invoice(
        json.dumps(_VALID_PAYLOAD), engine="gemini-3-flash", model="gemini-3-flash"
    )
    assert invoice.net_amount_confidence == "alta"
    assert invoice.tax_amount_confidence == "alta"


def test_irpf_se_parsea_separado_de_los_tramos_de_iva() -> None:
    payload = dict(
        _VALID_PAYLOAD,
        tax_lines=[{"base": 100.0, "rate": 21.0, "cuota": 21.0}],
        irpf_rate=19.0,
        irpf_amount=19.0,
    )

    invoice = parse_structured_invoice(json.dumps(payload), engine="gemini-3-flash", model="x")

    assert [line.rate for line in invoice.tax_lines] == [Decimal("21.0")]
    assert invoice.irpf_rate == Decimal("19.0")
    assert invoice.irpf_amount == Decimal("19.0")


def test_el_prompt_separa_irpf_y_conserva_tipos_de_iva_desconocidos() -> None:
    from ocr.extraction_json import EXTRACTION_PROMPT

    prompt = EXTRACTION_PROMPT.lower()
    assert "irpf_rate" in EXTRACTION_PROMPT
    assert "irpf_amount" in EXTRACTION_PROMPT
    assert "retención" in prompt
    assert "conserva cualquier tipo de iva numérico y finito" in prompt


def test_un_tipo_de_iva_desconocido_se_conserva_y_se_marca() -> None:
    payload = dict(_VALID_PAYLOAD, tax_lines=[{"base": 100, "rate": 19, "cuota": 19}])

    invoice = parse_structured_invoice(json.dumps(payload), engine="gemini-3-flash", model="x")

    assert invoice.tax_lines[0].rate == Decimal("19")
    assert invoice.raw["_unknown_tax_rates"] == ["19"]


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

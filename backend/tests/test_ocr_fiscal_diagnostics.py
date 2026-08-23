"""Diagnósticos fiscales detallados de R-037."""

from __future__ import annotations

from decimal import Decimal

from ocr.extraction_json import parse_structured_invoice
from ocr.verification import TaxLine, check_invoice_totals_detailed


def test_r037_detalla_cada_tramo_y_el_total() -> None:
    result = check_invoice_totals_detailed(
        [TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("21"))],
        Decimal("121"),
    )

    assert result.valid is True
    assert result.line_checks[0].expected_quota == Decimal("21")
    assert result.line_checks[0].actual_quota == Decimal("21")
    assert result.line_checks[0].delta == Decimal("0")
    assert result.total_delta == Decimal("0")


def test_r037_un_tipo_iva_no_conocido_se_conserva_y_se_marca() -> None:
    invoice = parse_structured_invoice(
        '{"schema_version":"1","tax_lines":[{"base":"100","rate":"7.5",'
        '"quota":"7.5"}]}',
        engine="test",
        model="test-1",
    )

    assert invoice.tax_lines[0].rate == Decimal("7.5")
    assert invoice.raw["_unknown_tax_rates"] == ["7.5"]

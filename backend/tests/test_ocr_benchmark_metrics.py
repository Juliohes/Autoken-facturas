"""Métricas observables del benchmark comparable R-032."""

from __future__ import annotations

from ocr.benchmark_metrics import calculate_metrics
from ocr.benchmark_scoring import score_combination

TRUTH = {
    "counterparty_tax_id": "B12345678",
    "counterparty_name": "Proveedor SA",
    "invoice_number": "F-2026-001",
    "issue_date": "2026-05-10",
    "total_amount": "121.00",
    "net_amount": "100.00",
    "tax_amount": "21.00",
    "tax_lines": [{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}],
}


def test_r032_calcula_exactitud_criticos_aritmetica_y_correcciones_estimadas() -> None:
    reading = {**TRUTH, "total_amount": "999.00"}
    score = score_combination(reading, TRUTH)

    metrics = calculate_metrics(
        score,
        reading,
        TRUTH,
        arithmetic_valid_after_extraction=False,
    )

    assert metrics.field_exact_accuracy == 7 / 8
    assert metrics.critical_field_accuracy == 3 / 4
    assert metrics.all_critical_exact is False
    assert metrics.tax_lines_accuracy is True
    assert metrics.arithmetic_valid_after_extraction is False
    assert metrics.manual_corrections_per_invoice == 1


def test_r032_marca_valores_leidos_sin_ground_truth_como_alucinaciones() -> None:
    truth = {**TRUTH, "invoice_number": None, "tax_lines": []}
    reading = {**TRUTH, "tax_lines": [{"iva_pct": "21", "base": "100", "cuota": "21"}]}
    score = score_combination(reading, truth)

    metrics = calculate_metrics(score, reading, truth, arithmetic_valid_after_extraction=None)

    assert metrics.hallucination_flags == ("invoice_number", "tax_lines")
    assert metrics.manual_corrections_per_invoice is None


def test_r032_no_fabrica_cero_para_metricas_sin_datos() -> None:
    reading = dict.fromkeys(TRUTH, None)
    truth = dict.fromkeys(TRUTH, None)
    score = score_combination(reading, truth)

    metrics = calculate_metrics(score, reading, truth, arithmetic_valid_after_extraction=None)

    assert metrics.field_exact_accuracy is None
    assert metrics.critical_field_accuracy is None
    assert metrics.all_critical_exact is None
    assert metrics.tax_lines_accuracy is None
    assert metrics.manual_corrections_per_invoice is None

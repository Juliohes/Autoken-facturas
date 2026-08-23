"""Comportamiento del score de confianza sistémica R-036."""

from __future__ import annotations

from decimal import Decimal

from ocr.analysis import analyze_invoice
from ocr.confidence import Evidence, compute_field_confidence
from tests._ocr import OWN_CIF, build_extracted


def test_r036_la_confianza_sistemica_explica_el_acuerdo_y_la_validacion() -> None:
    result = compute_field_confidence(
        Evidence(
            provider_confidence=1.0,
            primary_high=True,
            fallback_agrees=True,
            deterministic_valid=True,
            fallback_used=True,
        )
    )

    assert result.score == 1.0
    assert "primary_high" in result.reasons
    assert "engines_agree" in result.reasons
    assert "fallback_used" in result.reasons


def test_r036_validacion_fallida_limita_la_confianza() -> None:
    result = compute_field_confidence(
        Evidence(
            provider_confidence=1.0,
            primary_high=True,
            deterministic_invalid=True,
            deterministic_invalid_reason="invoice_math_failed",
        )
    )

    assert result.score <= 0.35
    assert "invoice_math_failed" in result.reasons


def test_r036_analysis_separa_la_etiqueta_existente_del_score_sistemico() -> None:
    analysis = analyze_invoice(build_extracted(total=Decimal("121.00")), OWN_CIF)

    assert analysis.confidences["total_amount"] == "alta"
    detail = analysis.confidences["_system_confidence"]["total_amount"]
    assert detail["provider_confidence"] == 1.0
    assert isinstance(detail["system_confidence"], float)
    assert "invoice_math_ok" in detail["reasons"]

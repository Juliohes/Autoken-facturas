"""Decisión pura de fallback condicional R-034."""

from __future__ import annotations

from decimal import Decimal

from ocr.analysis import analyze_invoice
from ocr.fallback import fallback_reasons, has_material_conflict
from tests._ocr import OWN_CIF, build_extracted


def test_r034_nombre_media_no_dispara_fallback_si_el_resto_es_solido() -> None:
    invoice = build_extracted(counterparty_name_conf="media")
    analysis = analyze_invoice(invoice, OWN_CIF)

    assert fallback_reasons(invoice, analysis) == ()


def test_r034_timeout_dispara_fallback() -> None:
    invoice = build_extracted()
    analysis = analyze_invoice(invoice, OWN_CIF)

    assert fallback_reasons(invoice, analysis, provider_error="provider_timeout") == (
        "provider_timeout",
    )


def test_r034_campo_critico_ausente_y_descuadre_disparan_fallback() -> None:
    invoice = build_extracted(counterparty_cif=None, total=Decimal("999.00"))
    analysis = analyze_invoice(invoice, OWN_CIF)

    assert fallback_reasons(invoice, analysis) == (
        "critical_field_missing",
        "invoice_math_mismatch",
    )


def test_r034_dos_valores_distintos_se_consideran_conflicto() -> None:
    primary = build_extracted()
    fallback = build_extracted(total=Decimal("120.00"))

    assert has_material_conflict(
        primary,
        fallback,
        analyze_invoice(primary, OWN_CIF),
        analyze_invoice(fallback, OWN_CIF),
    )

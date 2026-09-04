"""Comportamiento observable del consenso OCR R-035."""

from __future__ import annotations

from decimal import Decimal

from ocr.arbiter import FieldCandidate, FieldDecision, decide_field, reconcile
from ocr.normalization import (
    normalize_amount,
    normalize_date,
    normalize_invoice_number,
    normalize_name,
    normalize_tax_id,
)
from tests._ocr import build_extracted


def test_r035_normaliza_identificadores_importes_fecha_numero_y_nombre() -> None:
    assert normalize_tax_id("  b-123 456 78 ") == "B12345678"
    assert normalize_amount(Decimal("121.00")) == "121"
    assert normalize_date("2026-05-10") == "2026-05-10"
    assert normalize_invoice_number("  ab/01-2  ") == "AB/01-2"
    assert normalize_name("  Proveedor   S.A. ") == "proveedor s.a."


def test_r035_dos_motores_con_el_mismo_importe_formateado_son_un_acuerdo() -> None:
    candidates = [
        FieldCandidate("total_amount", "121", Decimal("121.00"), "primary", "p1", 1.0),
        FieldCandidate("total_amount", "121", Decimal("121"), "fallback", "p2", 0.8),
    ]

    decision = decide_field(candidates)

    assert isinstance(decision, FieldDecision)
    assert decision.status == "accepted"
    assert decision.value == Decimal("121.00")
    assert decision.sources == ["primary:p1", "fallback:p2"]
    assert "engines_agree" in decision.reasons


def test_r035_dos_valores_distintos_sin_margen_quedan_en_conflicto() -> None:
    decision = decide_field(
        [
            FieldCandidate("invoice_number", "A/1-2", "A/1-2", "primary", "p1", 1.0),
            FieldCandidate("invoice_number", "B/1-2", "B/1-2", "fallback", "p2", 1.0),
        ]
    )

    assert decision.status == "conflict"
    assert decision.value is None
    assert "engines_disagree" in decision.reasons


def test_r035_una_unica_lectura_baja_queda_dudosa() -> None:
    decision = decide_field(
        [FieldCandidate("total_amount", "121", Decimal("121"), "primary", "p1", 0.2)]
    )

    assert decision.status == "uncertain"
    assert decision.value is None


def test_r035_la_evidencia_del_proveedor_puede_desempatar() -> None:
    decision = decide_field(
        [
            FieldCandidate("counterparty_tax_id", "B123", "B123", "primary", "p1", 1.0),
            FieldCandidate("counterparty_tax_id", "A456", "A456", "fallback", "p2", 1.0),
        ],
        supplier_normalized_value="A456",
    )

    assert decision.status == "accepted"
    assert decision.value == "A456"
    assert "supplier_known" in decision.reasons


def test_r035_reconcile_conserva_el_valor_aceptado_y_deja_traza() -> None:
    primary = build_extracted(total=Decimal("121.00"), engine="primary", model="p1")
    fallback = build_extracted(total=Decimal("121"), engine="fallback", model="p2")

    reconciled = reconcile([primary, fallback], consensus_mode="per_field")

    assert reconciled.total_amount == Decimal("121.00")
    assert reconciled.raw["_consensus"]["total_amount"]["status"] == "accepted"
    assert reconciled.raw["_consensus"]["total_amount"]["sources"] == [
        "primary:p1",
        "fallback:p2",
    ]


def test_r035_modo_primary_only_no_promociona_el_fallback() -> None:
    primary = build_extracted(
        total=Decimal("121.00"), confidence="media", engine="primary", model="p1"
    )
    fallback = build_extracted(total=Decimal("120.00"), engine="fallback", model="p2")

    reconciled = reconcile([primary, fallback], consensus_mode="primary_only")

    assert reconciled.total_amount == Decimal("121.00")
    assert reconciled.engine == "primary"

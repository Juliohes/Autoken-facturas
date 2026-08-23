"""Features y límites de aprendizaje por proveedor de R-038."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from invoicing.supplier_profiles import (
    build_profile_features,
    profile_can_influence_decision,
    profile_evidence,
    supplier_profile_blind_index,
)


def test_r038_guarda_patrones_y_contadores_sin_guardar_la_factura_completa() -> None:
    features = build_profile_features(
        invoice_number="F-2026-004",
        tax_rates=[Decimal("21"), Decimal("10")],
        tax_line_count=2,
        corrections=[
            SimpleNamespace(field="total_amount"),
            SimpleNamespace(field="invoice_number"),
        ],
    )

    assert features.invoice_number_pattern == {"prefix": "F", "separator": "-", "suffix": "digits"}
    assert features.tax_rate_histogram == {"10": 1, "21": 1}
    assert features.tax_line_count_histogram == {"2": 1}
    assert features.field_correction_stats == {"invoice_number": 1, "total_amount": 1}
    assert "004" not in str(features)


def test_r038_el_indice_ciego_depende_de_tenant_y_empresa_y_no_expone_el_cif() -> None:
    settings = SimpleNamespace(db_encryption_master_key="test-master-key")
    tenant_id, company_id = uuid4(), uuid4()

    first = supplier_profile_blind_index(settings, tenant_id, company_id, "B-12345678")
    second = supplier_profile_blind_index(settings, tenant_id, uuid4(), "B12345678")

    assert first != second
    assert "12345678" not in first


def test_r038_cold_start_no_influye_hasta_tres_confirmaciones() -> None:
    assert profile_can_influence_decision(0) is False
    assert profile_can_influence_decision(2) is False
    assert profile_can_influence_decision(3) is True


def test_r038_perfil_maduro_detecta_un_tipo_de_iva_anomalo_sin_sobrescribirlo() -> None:
    evidence = profile_evidence(
        {
            "confirmations": 3,
            "invoice_number_patterns": [{"prefix": "F", "separator": "-", "suffix": "digits"}],
            "tax_rate_histogram": {"21": 4},
        },
        invoice_number="F-2026-005",
        tax_rates=[Decimal("10")],
    )

    assert evidence.supplier_known is True
    assert evidence.pattern_match is True
    assert evidence.tax_rate_conflict is True

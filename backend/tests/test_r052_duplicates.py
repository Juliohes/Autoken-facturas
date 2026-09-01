"""Tests puros de la decisión de duplicado de R-052."""

from decimal import Decimal

from invoicing.duplicates import DuplicateValues, duplicate_match


def test_c10_numero_dos_cif_importe_igual_es_duplicado_confirmado() -> None:
    # spec: C10
    current = DuplicateValues(" f-1 ", "B06183446", "A39031620", Decimal("121.00"))
    candidate = DuplicateValues("F-1", "b06183446", "a39031620", Decimal("121.00"))

    match = duplicate_match(current, candidate, uploaded_file_id="original", invoice_id="invoice-1")

    assert match is not None
    assert match.kind == "confirmed"
    assert match.matching_fields == (
        "invoice_number",
        "own_tax_id",
        "counterparty_tax_id",
        "total_amount",
    )


def test_c9_numero_y_dos_cif_sin_importe_igual_es_sospecha_bloqueante() -> None:
    # spec: C9
    current = DuplicateValues("F-1", "B06183446", "A39031620", Decimal("121.00"))
    candidate = DuplicateValues("F-1", "B06183446", "A39031620", Decimal("99.00"))

    match = duplicate_match(current, candidate, uploaded_file_id="original", invoice_id=None)

    assert match is not None
    assert match.kind == "suspected"


def test_c9_sin_uno_de_los_campos_requeridos_no_declara_duplicado() -> None:
    # spec: C9, invariant de campos ausentes
    current = DuplicateValues("F-1", "B06183446", None, Decimal("121.00"))
    candidate = DuplicateValues("F-1", "B06183446", "A39031620", Decimal("121.00"))

    assert duplicate_match(current, candidate, uploaded_file_id="original", invoice_id=None) is None

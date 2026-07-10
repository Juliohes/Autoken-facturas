"""El primitivo de validación fiscal/IBAN vive en `shared.tax_id` (#59).

Bloquea la nueva ubicación canónica del validador "tipo DNI" (movido desde `ocr.verification`): el
comportamiento no cambia. La cobertura exhaustiva de los algoritmos sigue en
`tests/test_ocr_verification.py` (que ahora importa por el reexport). Aquí solo se ancla que la
superficie pública responde desde `shared.tax_id` y que `ocr.verification` reexporta el objeto.
"""

from __future__ import annotations

from shared.tax_id import (
    CheckResult,
    normalize_tax_id,
    validate_cif,
    validate_iban,
    validate_nie,
    validate_nif,
    validate_tax_id,
)


def test_validadores_disponibles_en_shared() -> None:
    """Los validadores viven en `shared.tax_id` y devuelven el veredicto esperado."""
    assert validate_nif("12345678Z").valid
    assert validate_nie("X1234567L").valid
    assert validate_cif("A58818501").valid
    assert validate_tax_id("A58818501").valid
    assert validate_iban("ES9121000418450200051332").valid
    assert not validate_cif("A58818502").valid
    assert normalize_tax_id("a-58.818.501") == "A58818501"


def test_ocr_verification_reexporta_el_mismo_primitivo() -> None:
    """`ocr.verification` sigue funcionando reexportando el mismo objeto de `shared.tax_id`."""
    from ocr import verification

    assert verification.validate_tax_id is validate_tax_id
    assert verification.normalize_tax_id is normalize_tax_id
    assert verification.validate_iban is validate_iban
    assert verification.validate_nif is validate_nif
    assert verification.CheckResult is CheckResult

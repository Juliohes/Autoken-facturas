"""Evidencia Tesseract experimental R-039."""

from ocr.local_evidence.tesseract_checker import inspect_local_text


def test_r039_texto_local_encuentra_campos_sin_ser_fuente_de_verdad() -> None:
    evidence = inspect_local_text(
        "Proveedor SA\nCIF B12345678\nFactura F-2026-004\nFecha 2026-05-10\nTotal 121.00",
        {
            "counterparty_tax_id": "B-12345678",
            "invoice_number": "F-2026-004",
            "issue_date": "2026-05-10",
            "total_amount": "121.00",
        },
    )

    assert evidence.available is True
    assert evidence.matched_fields == {
        "counterparty_tax_id": True,
        "invoice_number": True,
        "issue_date": True,
        "total_amount": True,
    }


def test_r039_no_encontrar_un_campo_es_evidencia_debil_no_un_fallo() -> None:
    evidence = inspect_local_text("Factura sin importe legible", {"total_amount": "121.00"})

    assert evidence.available is True
    assert evidence.matched_fields == {"total_amount": False}


def test_r039_entrada_no_disponible_devuelve_evidencia_indeterminada() -> None:
    evidence = inspect_local_text(None, {"total_amount": "121.00"})

    assert evidence.available is False
    assert evidence.matched_fields == {"total_amount": None}

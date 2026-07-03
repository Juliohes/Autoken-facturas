"""Tests de normalización del scorer del bench OCR (1.2).

Comportamiento: comparar valores del ground truth con el texto del motor tolerando el formato
(coma/punto decimal, separadores de fecha, espacios y puntos en los CIF).
"""

from datetime import date
from decimal import Decimal

import pytest

from ocr.eval.normalize import (
    amount_variants,
    date_variants,
    normalize_tax_id,
    normalize_text,
    parse_amount,
)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("B-56922321", "B56922321"),
        ("b56922321", "B56922321"),
        ("  A87563888 ", "A87563888"),
        ("08835156.M", "08835156M"),
        ("ES B56922321", "ESB56922321"),
    ],
)
def test_normalize_tax_id_quita_ruido_y_sube_caja(entrada: str, esperado: str) -> None:
    assert normalize_tax_id(entrada) == esperado


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("996,40", Decimal("996.40")),
        ("996.40", Decimal("996.40")),
        ("1.234,56", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
        ("163,99 EUROS", Decimal("163.99")),
        ("  0,00 ", Decimal("0.00")),
    ],
)
def test_parse_amount_entiende_formatos_es_y_en(entrada: str, esperado: Decimal) -> None:
    assert parse_amount(entrada) == esperado


def test_amount_variants_genera_coma_y_punto() -> None:
    variantes = amount_variants(Decimal("996.40"))
    assert "996,40" in variantes
    assert "996.40" in variantes


def test_date_variants_cubre_formatos_habituales() -> None:
    variantes = date_variants(date(2026, 5, 18))
    assert "18/05/2026" in variantes
    assert "18-05-2026" in variantes
    assert "18.05.2026" in variantes
    assert "2026-05-18" in variantes


def test_normalize_text_permite_encontrar_cif_con_puntos_y_espacios() -> None:
    texto = "C.I.F.: B 569 223 21 emitido"
    assert "B56922321" in normalize_text(texto)

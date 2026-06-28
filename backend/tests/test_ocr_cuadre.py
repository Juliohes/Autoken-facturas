"""Tests de comportamiento BP-1: cuadre aritmético por tramo.

Spec: docs/specs/BP-1-cuadre-aritmetico-por-tramo.md
Cierra el agujero anti-alucinación: `check_invoice_totals` debe validar cada tramo
(`base x IVA% = cuota`) además del cuadre global. Diseño: value object `TaxLine` (Opción C).

Estos tests están en ROJO a propósito hasta que el implementer cree `TaxLine` y reescriba
`check_invoice_totals` con la nueva firma.
"""

from decimal import Decimal

from ocr.verification import TaxLine, check_invoice_totals

# --- Camino feliz (casos deseados) ---------------------------------------------------------


def test_factura_coherente_de_un_tramo_cuadra() -> None:
    # spec: C1 / DE1
    lines = [TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("21.00"))]
    assert check_invoice_totals(lines, Decimal("121.00")).valid


def test_multitramo_con_tipos_de_iva_distintos_cuadra() -> None:
    # spec: C6 / DE2
    lines = [
        TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("21")),
        TaxLine(base=Decimal("200"), iva_pct=Decimal("10"), cuota=Decimal("20")),
    ]
    assert check_invoice_totals(lines, Decimal("341")).valid


def test_tramo_exento_iva_cero_cuadra() -> None:
    # spec: §5 / DE2 (IVA 0% exento)
    lines = [TaxLine(base=Decimal("100"), iva_pct=Decimal("0"), cuota=Decimal("0"))]
    assert check_invoice_totals(lines, Decimal("100")).valid


def test_cuadre_global_con_irpf() -> None:
    # spec: C5 / DE3
    lines = [TaxLine(base=Decimal("1000"), iva_pct=Decimal("21"), cuota=Decimal("210"))]
    assert check_invoice_totals(lines, Decimal("1060"), irpf_cuota=Decimal("150")).valid


# --- Anti-alucinación (casos NO deseados) --------------------------------------------------


def test_cuota_de_tramo_que_no_deriva_de_base_por_iva_se_rechaza() -> None:
    # spec: C2 / ND1  (el agujero de BP-1)
    lines = [TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("25"))]
    result = check_invoice_totals(lines, Decimal("125"))
    assert not result.valid
    assert "tramo" in result.reason.lower()  # ND5: el motivo dice qué revisar


def test_errores_entre_tramos_que_se_compensan_en_el_total_se_detectan() -> None:
    # spec: C3 / ND2  (núcleo anti-alucinación)
    # Correcto: 100 x 21% = 21 por tramo; declaradas 25 y 17 (+4/-4) suman 42 = 21+21.
    lines = [
        TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("25")),
        TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("17")),
    ]
    # El total global cuadra (200 + 42 = 242), pero los tramos no.
    result = check_invoice_totals(lines, Decimal("242"))
    assert not result.valid


def test_descuadre_global_aunque_cada_tramo_cuadre_se_rechaza() -> None:
    # spec: C4 / ND3
    lines = [
        TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("21")),
        TaxLine(base=Decimal("200"), iva_pct=Decimal("10"), cuota=Decimal("20")),
    ]
    # Tramos cuadran; Σbase 300 + Σcuota 41 = 341, pero total declarado 350.
    result = check_invoice_totals(lines, Decimal("350"))
    assert not result.valid
    assert "total" in result.reason.lower()


def test_con_varios_tramos_malos_el_motivo_senala_el_primero() -> None:
    # spec: C8 / ND5  (fail-fast)
    lines = [
        TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("25")),  # tramo 1 malo
        TaxLine(base=Decimal("200"), iva_pct=Decimal("10"), cuota=Decimal("30")),  # tramo 2 malo
    ]
    result = check_invoice_totals(lines, Decimal("355"))  # 300 + (25+30) = 355: global cuadra
    assert not result.valid
    assert "1" in result.reason  # identifica el primer tramo descuadrado


# --- Bordes de tolerancia (casos límite) ---------------------------------------------------


def test_tramo_en_el_borde_de_tolerancia_se_acepta() -> None:
    # spec: C7 / DE4  (diferencia por tramo == 0,02 -> válida)
    lines = [TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("21.02"))]
    assert check_invoice_totals(lines, Decimal("121.02")).valid


def test_tramo_pasado_el_borde_de_tolerancia_se_rechaza() -> None:
    # spec: C7 / ND6  (diferencia por tramo == 0,03 -> inválida; caza el cambio > -> >=)
    lines = [TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("21.03"))]
    assert not check_invoice_totals(lines, Decimal("121.03")).valid


def test_total_en_el_borde_de_tolerancia_global_se_acepta() -> None:
    # spec: C7 / DE4  (diferencia global == 0,02 -> válida)
    lines = [TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("21"))]
    assert check_invoice_totals(lines, Decimal("121.02")).valid


def test_total_pasado_el_borde_de_tolerancia_global_se_rechaza() -> None:
    # spec: C7 / ND6  (diferencia global == 0,03 -> inválida)
    lines = [TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("21"))]
    assert not check_invoice_totals(lines, Decimal("121.03")).valid


# --- Factura sin tramos (caso límite) ------------------------------------------------------


def test_factura_sin_tramos_con_total_cero_es_valida() -> None:
    # spec: §5 / DE6
    assert check_invoice_totals([], Decimal("0")).valid


def test_factura_sin_tramos_con_total_no_cero_se_rechaza() -> None:
    # spec: §5
    assert not check_invoice_totals([], Decimal("10")).valid


# --- Importes no finitos: NaN/Infinity (anti-alucinación, hallazgo H1) ----------------------


def test_cuota_no_finita_nan_se_rechaza() -> None:
    # spec: C9
    lines = [TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("NaN"))]
    assert not check_invoice_totals(lines, Decimal("121")).valid


def test_base_no_finita_nan_se_rechaza() -> None:
    # spec: C9
    lines = [TaxLine(base=Decimal("NaN"), iva_pct=Decimal("21"), cuota=Decimal("21"))]
    assert not check_invoice_totals(lines, Decimal("121")).valid


def test_total_no_finito_nan_se_rechaza() -> None:
    # spec: C9
    lines = [TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("21"))]
    assert not check_invoice_totals(lines, Decimal("NaN")).valid


def test_total_infinito_se_rechaza() -> None:
    # spec: C9
    lines = [TaxLine(base=Decimal("100"), iva_pct=Decimal("21"), cuota=Decimal("21"))]
    assert not check_invoice_totals(lines, Decimal("Infinity")).valid


def test_factura_sin_tramos_con_total_no_finito_se_rechaza() -> None:
    # spec: C9
    assert not check_invoice_totals([], Decimal("NaN")).valid

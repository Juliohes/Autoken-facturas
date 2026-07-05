"""Tests del scorer de lectura del bench OCR (1.2).

Comportamiento observable: dado un ground truth y el texto que devolvió un motor, el scorer dice
qué campos capturó el motor (recall), tolerando el formato. No se ata al concepto de contraparte.
"""

from ocr.eval.models import GroundTruth, Party
from ocr.eval.scorer import aggregate_by_engine, field_recall_by_engine, score_reading

_GT = GroundTruth(
    invoice_id="factura-2",
    source_file="factura-2.pdf",
    parties=(
        Party(role="issuer", name="LUMAPA2 BROKERS SL", tax_id="B56922321"),
        Party(role="recipient", name="HISPALAR NEW CENTURY S.A.", tax_id="A87563888"),
    ),
    issue_date="2026-05-18",
    total_amount="996.40",
)


def test_motor_que_lee_todo_tiene_recall_total() -> None:
    """Un texto que contiene ambos CIF, la fecha y el total puntúa 1.0."""
    texto = "LUMAPA2 B56922321 ... HISPALAR A87563888 ... 18/05/2026 ... TOTAL 996,40 EUR"
    score = score_reading(_GT, texto, engine="mistral-ocr-4")
    assert score.recall == 1.0
    assert all(r.found for r in score.results)


def test_cif_no_leido_baja_el_recall_y_se_marca_ese_campo() -> None:
    """Si falta un CIF, ese FieldResult queda en found=False y el recall baja."""
    texto = "LUMAPA2 B56922321 ... 18/05/2026 ... TOTAL 996,40 EUR"  # falta A87563888
    score = score_reading(_GT, texto, engine="mistral-ocr-4")
    fallidos = [r for r in score.results if not r.found]
    assert len(fallidos) == 1
    assert fallidos[0].expected == "A87563888"
    assert score.recall < 1.0


def test_importe_en_formato_punto_tambien_cuenta() -> None:
    """El total escrito con punto decimal se reconoce igual que con coma."""
    texto = "B56922321 A87563888 2026-05-18 total 996.40"
    score = score_reading(_GT, texto, engine="x")
    total = next(r for r in score.results if r.field == "total_amount")
    assert total.found


def test_cif_con_puntos_y_espacios_en_el_texto_cuenta() -> None:
    """El motor puede escribir el CIF con puntos/espacios; sigue siendo un acierto."""
    texto = "C.I.F.: B 569 223 21 y A-87563888 fecha 18/05/2026 total 996,40"
    score = score_reading(_GT, texto, engine="x")
    cifs = [r for r in score.results if r.field == "tax_id"]
    assert all(r.found for r in cifs)


def test_agregado_por_motor_promedia_recall_de_varias_facturas() -> None:
    """El agregado combina el recall de todas las facturas de un mismo motor."""
    bueno = score_reading(_GT, "B56922321 A87563888 18/05/2026 996,40", engine="m")
    malo = score_reading(_GT, "B56922321", engine="m")  # solo 1 de 4
    agg = aggregate_by_engine([bueno, malo])
    assert agg["m"].invoices == 2
    assert 0.0 < agg["m"].recall < 1.0
    # recall específico de tax_id: bueno acierta 2/2, malo 1/2 -> 3/4
    assert agg["m"].tax_id_recall == 0.75


def test_recall_por_campo_desglosa_cada_tipo_de_campo() -> None:
    """El desglose por campo da un recall separado para tax_id, fecha y total de cada motor."""
    bueno = score_reading(_GT, "B56922321 A87563888 18/05/2026 996,40", engine="m")
    malo = score_reading(_GT, "B56922321 18/05/2026", engine="m")  # falta 1 CIF y el total
    breakdown = field_recall_by_engine([bueno, malo])
    assert breakdown["m"]["tax_id"] == 0.75  # 3 de 4 CIF entre las dos facturas
    assert breakdown["m"]["issue_date"] == 1.0  # la fecha aparece en ambas
    assert breakdown["m"]["total_amount"] == 0.5  # solo la buena trae el total

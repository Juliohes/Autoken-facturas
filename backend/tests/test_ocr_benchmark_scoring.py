"""Tests de comportamiento S6.7 Área B (puntuación), spec
docs/specs/S6.7-benchmark-real-motor-variante.md, C5-C9.

Unit puro (sin red, sin Postgres): `score_combination` compara la lectura de UNA combinación
(variante, motor) contra la verdad confirmada, campo a campo, reutilizando `ocr.field_matching`
(S6.6) para todo salvo la tolerancia del 2% en tramos de IVA (exclusiva de esta tarea). `reading`/
`truth` son diccionarios con las mismas claves de dominio que ya usa el resto del proyecto:
`counterparty_tax_id`, `counterparty_name`, `invoice_number`, `issue_date`, `total_amount`,
`net_amount`, `tax_amount`, `tax_lines` (lista de `{iva_pct, base, cuota}`).
"""

from __future__ import annotations

from ocr.benchmark_scoring import score_combination

TRUTH = {
    "counterparty_tax_id": "B12345678",
    "counterparty_name": "Proveedor SA",
    "invoice_number": "F-2026-001",
    "issue_date": "2026-05-10",
    "total_amount": "121.00",
    "net_amount": "100.00",
    "tax_amount": "21.00",
    "tax_lines": [{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}],
}


def _field(score, field: str):
    return next(f for f in score.field_scores if f.field == field)


def test_c9_una_lectura_identica_a_la_verdad_acierta_en_todo() -> None:
    """spec: C9 -- se guarda un desglose acierto/fallo por campo, no solo un ratio agregado."""
    score = score_combination(dict(TRUTH), TRUTH)

    assert all(f.match is True for f in score.field_scores)
    assert score.tax_lines_matched is True
    assert score.comparables == 8  # 7 campos escalares + el grupo de tramos de IVA
    assert score.aciertos == 8


def test_c5_un_campo_sin_valor_confirmado_no_puntua_ni_a_favor_ni_en_contra() -> None:
    """spec: C5 -- invoice_number nunca rellenado por el humano: no cuenta en `comparables`."""
    truth = {**TRUTH, "invoice_number": None}
    reading = {**TRUTH, "invoice_number": "cualquier-cosa-inventada"}

    score = score_combination(reading, truth)

    assert _field(score, "invoice_number").match is None
    assert score.comparables == 7  # los otros 6 campos + tramos de IVA, sin invoice_number
    assert score.aciertos == 7


def test_c6_un_importe_con_formato_distinto_pero_mismo_valor_cuenta_como_acierto() -> None:
    """spec: C6 -- reutiliza el módulo de S6.6 (`amounts_match`), sin lógica propia duplicada."""
    reading = {**TRUTH, "total_amount": "121"}  # verdad: "121.00"

    score = score_combination(reading, TRUTH)

    assert _field(score, "total_amount").match is True


def test_c7_un_tramo_de_iva_con_medio_por_ciento_de_diferencia_cuenta_como_acierto() -> None:
    """spec: C7 -- tolerancia del 2% exclusiva del benchmark, solo en base/cuota del tramo."""
    reading = {**TRUTH, "tax_lines": [{"iva_pct": "21", "base": "100.50", "cuota": "21.00"}]}

    score = score_combination(reading, TRUTH)  # verdad: base 100.00 (0.5% de diferencia)

    assert score.tax_lines_matched is True
    assert score.aciertos == 8


def test_c7_un_tramo_de_iva_por_encima_del_2_por_ciento_no_cuenta_como_acierto() -> None:
    reading = {**TRUTH, "tax_lines": [{"iva_pct": "21", "base": "103.00", "cuota": "21.00"}]}

    score = score_combination(reading, TRUTH)  # verdad: base 100.00 (3% de diferencia)

    assert score.tax_lines_matched is False
    assert score.aciertos == 7


def test_c8_un_tramo_con_distinto_porcentaje_nunca_cuenta_como_acierto_aunque_los_importes_cuadren() -> (  # noqa: E501
    None
):
    """spec: C8 -- el 10% no coincide con el 21% real aunque base/cuota sean IDÉNTICOS, sin
    tolerancia posible sobre la propia tasa."""
    reading = {**TRUTH, "tax_lines": [{"iva_pct": "10", "base": "100.00", "cuota": "21.00"}]}

    score = score_combination(reading, TRUTH)

    assert score.tax_lines_matched is False


def test_un_campo_no_leido_por_el_motor_nunca_se_inventa_cuenta_como_fallo() -> None:
    """Anti-alucinación (spec §4): un motor que no leyó un campo (`None`) nunca puede "acertar por
    casualidad" -- cuenta como fallo real si la verdad SÍ tiene valor, nunca se descarta como si
    fuera "no comparable" solo porque el motor no lo leyó."""
    reading = {**TRUTH, "counterparty_tax_id": None}

    score = score_combination(reading, TRUTH)

    assert _field(score, "counterparty_tax_id").match is False
    assert score.comparables == 8


def test_un_campo_con_tipo_inesperado_en_reading_nunca_lanza_y_cuenta_como_fallo() -> None:
    """Auditoría S6.7 (patrones+seguridad, ALTO): `reading` es la salida directa, NO confiable, de
    un motor OCR/LLM real -- una lista, un dict o un entero en cualquier campo son formas válidas
    que un motor puede devolver por error o por un mapeo distinto. `score_combination` nunca debe
    lanzar `AttributeError`; ese campo cuenta como fallo real, igual que "no leído"."""
    reading = {
        **TRUTH,
        "total_amount": [1, 2, 3],  # comparador de importe
        "issue_date": {"unexpected": "dict"},  # comparador de fecha
        "counterparty_tax_id": 12345,  # comparador de texto (CIF)
    }

    score = score_combination(reading, TRUTH)  # no debe lanzar

    assert _field(score, "total_amount").match is False
    assert _field(score, "issue_date").match is False
    assert _field(score, "counterparty_tax_id").match is False
    assert score.comparables == 8  # siguen siendo comparables (la verdad sí tiene valor)


def test_truth_tax_lines_con_tipo_no_lista_no_es_comparable_ni_acierta_por_vacuidad() -> None:
    """Auditoría S6.7 (patrones+seguridad, medio): un `truth["tax_lines"]` corrupto (no-lista pero
    truthy) NUNCA debe descartarse en silencio a `[]` -- eso haría que la combinación puntuara como
    "acierto" en tramos de IVA con datos de verdad corruptos. Debe tratarse como "no comparable",
    igual que si no hubiera tramos en absoluto."""
    truth = {**TRUTH, "tax_lines": "esto no es una lista"}

    score = score_combination(TRUTH, truth)

    assert score.tax_lines_matched is None
    assert score.comparables == 7


def test_truth_sin_tax_lines_en_absoluto_no_es_comparable() -> None:
    """spec: C5, mismo criterio general -- sin verdad de tramos de IVA, ese grupo no cuenta en
    `comparables` (ya documentado en `_score_tax_lines`, solo le faltaba el test)."""
    truth = {k: v for k, v in TRUTH.items() if k != "tax_lines"}

    score = score_combination(TRUTH, truth)

    assert score.tax_lines_matched is None
    assert score.comparables == 7

    truth_empty = {**TRUTH, "tax_lines": []}

    score_empty = score_combination(TRUTH, truth_empty)

    assert score_empty.tax_lines_matched is None
    assert score_empty.comparables == 7

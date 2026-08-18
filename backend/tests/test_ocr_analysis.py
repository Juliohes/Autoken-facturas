"""Tests de comportamiento S6.14: confianza separada de contraparte + captura ilegible.

Spec: docs/specs/S6.14-captura-alta-resolucion-y-confianza-nombre.md (backend, C4/C6/C7).

Módulo PURO (`ocr.analysis`): sin Postgres, sin red. Se ejercita `analyze_invoice` (comportamiento
observable, no los métodos internos) con el mismo doble `build_extracted` que usa el resto de la
suite OCR (`tests._ocr`).
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from ocr.analysis import STATUS_AUTO_OK, STATUS_HARD_FAIL, STATUS_NEEDS_REVIEW, analyze_invoice
from ocr.extraction import ExtractedTaxId
from tests._ocr import COUNTERPARTY_CIF, INVALID_COUNTERPARTY_CIF, OWN_CIF, build_extracted

# --- C4: la contraparte se elige por `value_confidence`, no por una confianza combinada ----------


def test_c4_la_contraparte_elegida_es_la_de_mayor_value_confidence() -> None:
    """Con dos identificadores leídos (ninguno el propio), gana el de mayor `value_confidence`,
    aunque su `name_confidence` sea peor que el del otro candidato: lo que decide CUÁL es la
    contraparte es la confianza del CIF, no la del nombre asociado."""
    base = build_extracted(counterparty_cif=None)  # sin contraparte por defecto; se añaden 2 a mano
    mejor_cif_peor_nombre = ExtractedTaxId(
        value=COUNTERPARTY_CIF,
        name="Comercial SL",
        value_confidence="alta",
        name_confidence="baja",
    )
    peor_cif_mejor_nombre = ExtractedTaxId(
        value=INVALID_COUNTERPARTY_CIF,
        name="Razón Social Legal SL",
        value_confidence="media",
        name_confidence="alta",
    )
    invoice = replace(base, tax_ids=(*base.tax_ids, peor_cif_mejor_nombre, mejor_cif_peor_nombre))

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.counterparty_tax_id == COUNTERPARTY_CIF


# --- C4/C5: el enrutado exige alta en el CIF pero acepta media en el nombre ----------------------


def test_c4_nombre_con_confianza_media_no_bloquea() -> None:
    invoice = build_extracted(counterparty_value_conf="alta", counterparty_name_conf="media")

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.status == STATUS_AUTO_OK


def test_c4_nombre_con_confianza_baja_bloquea() -> None:
    invoice = build_extracted(counterparty_value_conf="alta", counterparty_name_conf="baja")

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.status == STATUS_NEEDS_REVIEW


def test_c4_nombre_no_legible_bloquea() -> None:
    invoice = build_extracted(
        counterparty_name=None, counterparty_value_conf="alta", counterparty_name_conf="alta"
    )

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.status == STATUS_NEEDS_REVIEW


def test_c4_cif_de_contraparte_con_confianza_media_bloquea_sin_relajar() -> None:
    """El CIF sigue exigiendo `alta` sin excepción, aunque el nombre sea perfecto (impacto fiscal
    real vs corrección visual barata: dato empírico del bench S6.7, CIF 89,66% vs nombre 58,62%)."""
    invoice = build_extracted(counterparty_value_conf="media", counterparty_name_conf="alta")

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.status == STATUS_NEEDS_REVIEW


# --- `confidences` incluye ahora la confianza del nombre de contraparte ---------------------------


def test_confidences_incluye_counterparty_name() -> None:
    invoice = build_extracted(counterparty_value_conf="alta", counterparty_name_conf="media")

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.confidences["counterparty_name"] == "media"


def test_confidences_counterparty_name_es_none_sin_contraparte() -> None:
    invoice = build_extracted(counterparty_cif=None, total=Decimal("100.00"), tax=None, net=None)

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.confidences["counterparty_name"] is None


# --- C6: una validación determinista fallida degrada la confianza PERSISTIDA ----------------------


def test_c6_mod23_invalido_degrada_la_confianza_del_cif_a_baja() -> None:
    invoice = build_extracted(counterparty_cif=INVALID_COUNTERPARTY_CIF, counterparty_conf="alta")

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.confidences["counterparty_tax_id"] == "baja"


def test_c6_cuadre_fallido_degrada_la_confianza_del_total_a_baja() -> None:
    invoice = build_extracted(total=Decimal("999.00"))  # no cuadra con net=100/tax=21

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.confidences["total_amount"] == "baja"


def test_c6_la_degradacion_no_toca_el_extracted_invoice_original() -> None:
    """La degradación vive SOLO en `confidences` (lo persistido/mostrado); el `ExtractedInvoice`
    original (lo que dijo el motor) se conserva intacto para trazabilidad/auditoría (S6.2)."""
    invoice = build_extracted(counterparty_cif=INVALID_COUNTERPARTY_CIF, counterparty_conf="alta")

    analyze_invoice(invoice, OWN_CIF)

    counterparty = next(tid for tid in invoice.tax_ids if tid.value == INVALID_COUNTERPARTY_CIF)
    assert counterparty.value_confidence == "alta"  # intacto: la etiqueta original del motor


def test_c6_validacion_ok_no_degrada() -> None:
    invoice = build_extracted()  # feliz: mód-23 válido y cuadre correcto

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.confidences["counterparty_tax_id"] == "alta"
    assert analysis.confidences["total_amount"] == "alta"


# --- C7: captura ilegible (hard_fail) -------------------------------------------------------------


def test_c7_hard_fail_cuando_los_3_fundamentales_no_se_leen() -> None:
    """Criterio (a): contraparte, total y fecha, ninguno leído a la vez."""
    invoice = build_extracted(counterparty_cif=None, total=None, issue_date=None)

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.status == STATUS_HARD_FAIL


def test_c7_hard_fail_pese_a_un_tramo_de_iva_con_confianza_alta() -> None:
    """Caso límite (spec §5): si los 3 fundamentales fallan, sigue siendo hard_fail aunque OTRO
    campo (aquí: base/IVA) tenga confianza alta -- el criterio (a) no mira los demás campos."""
    invoice = build_extracted(
        counterparty_cif=None,
        total=None,
        issue_date=None,
        net_confidence="alta",
        tax_confidence="alta",
    )

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.status == STATUS_HARD_FAIL


def test_c7_hard_fail_cuando_el_100_por_cien_de_los_campos_con_valor_es_baja() -> None:
    """Criterio (b): todo tiene valor, pero el motor se declara "baja" en el 100% de ello."""
    invoice = build_extracted(confidence="baja", counterparty_conf="baja")

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.status == STATUS_HARD_FAIL


def test_c7_no_hard_fail_si_al_menos_un_campo_no_es_baja() -> None:
    """Si el CIF de contraparte SÍ tiene confianza alta, ya no es 100% baja: no es hard_fail (cae
    a needs_review, no a auto_ok, porque el resto de campos siguen en baja)."""
    invoice = build_extracted(confidence="baja", counterparty_conf="alta")

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.status == STATUS_NEEDS_REVIEW


def test_c7_needs_review_normal_no_es_hard_fail() -> None:
    """El caso ya cubierto (contraparte no legible, pero total/fecha SÍ) sigue siendo needs_review,
    no hard_fail: no se cumplen los 3 fundamentales a la vez ni el 100% de confianza baja."""
    invoice = build_extracted(counterparty_cif=None)

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.status == STATUS_NEEDS_REVIEW


def test_c7_factura_legible_no_es_hard_fail() -> None:
    invoice = build_extracted()

    analysis = analyze_invoice(invoice, OWN_CIF)

    assert analysis.status == STATUS_AUTO_OK

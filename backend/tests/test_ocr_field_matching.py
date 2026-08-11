"""Tests de comportamiento S6.6 Área A (docs/specs/S6.6-laboratorio-comparacion-honesta.md, C1-C2) +
S6.7 C7/C8 (docs/specs/S6.7-benchmark-real-motor-variante.md, tolerancia del 2% en tramos de IVA,
exclusiva del benchmark -- S6.6 sigue usando igualdad exacta en todos sus criterios).

Unit puro (sin red, sin Postgres): el comportamiento es de una función de dominio (spec §5 de la
skill tdd-behavior), reutilizada por `invoicing.corrections` (C3, verificado por regresión sobre su
propia suite, no aquí) y por el benchmark de S6.7.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ocr.field_matching import (
    amounts_match,
    amounts_match_within_tolerance,
    dates_match,
    names_match,
    tax_ids_match,
    tax_lines_match,
    texts_match,
)

# --- amounts_match -----------------------------------------------------------------------------


def test_c1_un_importe_con_formato_distinto_pero_mismo_valor_cuenta_como_acierto() -> None:
    """spec: C1 -- "21" y "21,0" son el mismo importe, aunque el texto sea distinto."""
    assert amounts_match("21", "21,0") is True


def test_importes_con_punto_decimal_tambien_coinciden() -> None:
    """Formato "americano" (punto decimal), el que usa Pydantic/nuestra propia API."""
    assert amounts_match("121.00", "121") is True


def test_importes_ya_parseados_como_decimal_coinciden_por_valor() -> None:
    """`diff_corrections` llama a este módulo con `Decimal` ya tipado, no solo con texto."""
    assert amounts_match(Decimal("121.00"), Decimal("121")) is True


def test_dos_importes_realmente_distintos_no_coinciden() -> None:
    assert amounts_match("121.00", "120.00") is False


def test_cero_es_un_valor_real_y_compara_bien() -> None:
    """Cero no es "ausente": IRPF a 0 leído como "0" y confirmado como "0,00" debe coincidir."""
    assert amounts_match("0", "0,00") is True


def test_importes_negativos_comparan_por_valor_como_cualquier_otro() -> None:
    """Facturas rectificativas pueden llevar importes negativos; sin caso especial, el signo forma
    parte del valor decimal como otro cualquiera."""
    assert amounts_match("-50,00", "-50.00") is True
    assert amounts_match("-50,00", "50.00") is False


def test_una_coma_ambigua_de_miles_no_se_convierte_a_la_ciega(caplog=None) -> None:
    """Mismo criterio anti-ambigüedad que S6.1 (frontend): una coma con 3+ dígitos detrás no se
    interpreta como separador decimal (podría ser de miles) -- un valor que no se puede parsear con
    seguridad NUNCA cuenta como acierto, por si acaso, en vez de arriesgarse a una conversión ~1000x
    distinta y aun así decir que "coincide"."""
    assert amounts_match("1,234", "1234") is False


def test_ambos_lados_ausentes_no_es_un_fallo(caplog=None) -> None:
    """Dos campos ausentes no deberían compararse en la práctica (spec C8, "no comparable"), pero
    la función en sí no debe lanzar ni decir "no coinciden" por un caso que no le corresponde
    decidir -- devuelve True (nada que objetar) y quien la llama decide si el campo era
    comparable."""
    assert amounts_match(None, None) is True


def test_un_lado_ausente_y_el_otro_con_valor_no_coincide() -> None:
    assert amounts_match(None, "121.00") is False
    assert amounts_match("121.00", None) is False


def test_texto_no_numerico_no_coincide_con_nada_ni_siquiera_consigo_mismo_repetido() -> None:
    """Un motor que devuelve basura ("no leído", "N/A") en el importe: nunca cuenta como acierto,
    ni comparado contra otra basura igual -- anti-alucinación, no se inventa un "coinciden"
    barato."""
    assert amounts_match("no leído", "no leído") is False


# --- dates_match ---------------------------------------------------------------------------------


def test_c_fechas_iguales_coinciden_aunque_una_sea_texto_y_otra_date() -> None:
    assert dates_match("2026-05-10", date(2026, 5, 10)) is True


def test_fechas_distintas_no_coinciden() -> None:
    assert dates_match("2026-05-10", "2026-05-11") is False


def test_fecha_con_formato_invalido_no_coincide() -> None:
    assert dates_match("10/05/2026", "2026-05-10") is False


# --- tax_ids_match -------------------------------------------------------------------------------


def test_c2_un_cif_con_distintas_mayusculas_y_espacios_cuenta_como_acierto() -> None:
    """spec: C2."""
    assert tax_ids_match("b12345678", "B12345678") is True
    assert tax_ids_match(" B-1234567-8 ", "B12345678") is True


def test_dos_cif_distintos_no_coinciden() -> None:
    assert tax_ids_match("B12345678", "A87654321") is False


# --- names_match ---------------------------------------------------------------------------------


def test_nombre_con_espacios_de_mas_cuenta_como_acierto() -> None:
    assert names_match("Proveedor   SA", "  Proveedor SA  ") is True


def test_nombre_con_mayusculas_distintas_NO_se_normaliza_a_proposito() -> None:
    """A diferencia del CIF, el nombre de contraparte no se pasa a mayúsculas (mismo criterio que
    `invoicing.corrections._norm_name` hoy, que solo colapsa espacios) -- un cambio de
    capitalización real del proveedor sí debe verse como una diferencia real."""
    assert names_match("Proveedor SA", "PROVEEDOR SA") is False


# --- texts_match (número de factura y similares) ---------------------------------------------


def test_texts_match_es_comparacion_exacta_sin_normalizar() -> None:
    """`invoice_number` se compara tal cual hoy en `diff_corrections` (sin recortar espacios ni
    cambiar mayúsculas) -- mantenerlo así evita un cambio de comportamiento silencioso (spec C3)."""
    assert texts_match("F-2026-001", "F-2026-001") is True
    assert texts_match("F-2026-001", "f-2026-001") is False
    assert texts_match(" F-2026-001", "F-2026-001") is False


# --- amounts_match_within_tolerance (S6.7 C7, exclusiva del benchmark, nunca de S6.6) -----------


def test_s67_c7_un_importe_dentro_del_2_por_ciento_cuenta_como_acierto() -> None:
    """spec: S6.7 C7 -- 100,50 vs 100,00 es un 0,5% de diferencia, dentro del 2% de tolerancia."""
    assert amounts_match_within_tolerance("100,50", "100.00", tolerance=Decimal("0.02")) is True


def test_un_importe_justo_en_el_borde_del_2_por_ciento_cuenta_como_acierto() -> None:
    assert amounts_match_within_tolerance("102.00", "100.00", tolerance=Decimal("0.02")) is True


def test_un_importe_por_encima_del_2_por_ciento_no_cuenta_como_acierto() -> None:
    assert amounts_match_within_tolerance("103.00", "100.00", tolerance=Decimal("0.02")) is False


def test_valor_identico_siempre_cuenta_aunque_la_tolerancia_sea_cero() -> None:
    assert amounts_match_within_tolerance("100.00", "100.00", tolerance=Decimal("0")) is True


def test_ambos_lados_ausentes_no_es_un_fallo_con_tolerancia() -> None:
    assert amounts_match_within_tolerance(None, None, tolerance=Decimal("0.02")) is True


def test_un_lado_ausente_con_tolerancia_no_coincide() -> None:
    assert amounts_match_within_tolerance(None, "100.00", tolerance=Decimal("0.02")) is False


def test_contra_un_importe_confirmado_de_cero_no_hay_tolerancia_relativa_posible() -> None:
    """0 no admite un % relativo (división por cero) -- solo coincide si el otro lado es TAMBIÉN
    cero exacto, nunca por "estar cerca" de cero."""
    assert amounts_match_within_tolerance("0.50", "0.00", tolerance=Decimal("0.02")) is False
    assert amounts_match_within_tolerance("0.00", "0.00", tolerance=Decimal("0.02")) is True


# --- tax_lines_match con un comparador de importes distinto (S6.7 C7/C8) -------------------------


def test_s67_c7_tax_lines_match_admite_un_comparador_de_importes_con_tolerancia() -> None:
    """spec: S6.7 C7 -- mismo algoritmo de emparejamiento por `iva_pct` que S6.6 (sin duplicarlo),
    solo cambia CÓMO se comparan los importes dentro del tramo ya emparejado."""
    baseline = [(Decimal("21"), Decimal("100.50"), Decimal("21.00"))]
    confirmed = [(Decimal("21"), Decimal("100.00"), Decimal("21.00"))]

    def _tolerant(a: Decimal | None, b: Decimal | None) -> bool:
        return amounts_match_within_tolerance(a, b, tolerance=Decimal("0.02"))

    assert tax_lines_match(baseline, confirmed) is False  # S6.6 por defecto: exacto, sin tolerancia
    assert tax_lines_match(baseline, confirmed, amount_matcher=_tolerant) is True


def test_s67_c8_un_tramo_con_distinto_porcentaje_nunca_coincide_aunque_los_importes_cuadren() -> (
    None
):  # noqa: E501
    """spec: S6.7 C8 -- la tolerancia SOLO se aplica a base/cuota de un tramo ya emparejado por
    `iva_pct` exacto; un tramo al 10% nunca "coincide" con uno al 21%, con o sin tolerancia."""
    baseline = [(Decimal("10"), Decimal("100.00"), Decimal("10.00"))]
    confirmed = [(Decimal("21"), Decimal("100.00"), Decimal("21.00"))]

    def _tolerant(a: Decimal | None, b: Decimal | None) -> bool:
        return amounts_match_within_tolerance(a, b, tolerance=Decimal("0.02"))

    assert tax_lines_match(baseline, confirmed, amount_matcher=_tolerant) is False


# --- amounts_match_within_tolerance con NaN/Infinity (S6.7 auditoría, ronda 3, hallazgo ALTO) ---


def test_nan_en_un_lado_de_la_tolerancia_no_lanza_y_nunca_cuenta_como_acierto() -> None:
    """`Decimal("nan")` parsea sin error (no es un fallo de formato) pero no es seguro de operar --
    sin la guarda, `max(abs(parsed_a), abs(parsed_b))` revienta con `decimal.InvalidOperation` en
    cuanto uno de los dos lados es `NaN`."""
    assert amounts_match_within_tolerance("nan", "100.00", tolerance=Decimal("0.02")) is False
    assert amounts_match_within_tolerance("100.00", "NaN", tolerance=Decimal("0.02")) is False


def test_nan_contra_si_mismo_no_cuenta_como_acierto() -> None:
    """Anti-alucinación: ni siquiera "coincidir consigo mismo" salva a un valor no interpretable
    con seguridad."""
    assert amounts_match_within_tolerance("nan", "nan", tolerance=Decimal("0.02")) is False


def test_infinity_contra_si_mismo_no_cuenta_como_acierto() -> None:
    """A diferencia de `NaN`, `Decimal("Infinity") == Decimal("Infinity")` da `True` sin lanzar --
    sin la guarda de `is_finite()` ANTES del atajo de igualdad exacta, este caso colaría como
    acierto."""
    assert amounts_match_within_tolerance("Infinity", "Infinity", tolerance=Decimal("0.02")) is (
        False
    )


def test_infinity_en_un_lado_no_lanza_y_nunca_cuenta_como_acierto() -> None:
    assert amounts_match_within_tolerance("Infinity", "100.00", tolerance=Decimal("0.02")) is False
    assert amounts_match_within_tolerance("-Infinity", "0.00", tolerance=Decimal("0.02")) is False


# --- amounts_match (S6.6) con NaN/Infinity: verificado, no necesita la misma guarda -------------


def test_amounts_match_s66_con_nan_no_lanza_y_no_cuenta_como_acierto() -> None:
    """`amounts_match` solo hace `==` (nunca divide), que no lanza con `NaN` -- verificado aquí
    antes de decidir que NO hace falta tocar esta función (S6.7 auditoría, ronda 3): `NaN == NaN`
    da `False` en Python/`Decimal`, así que ni siquiera comparado consigo mismo cuenta como
    acierto."""
    assert amounts_match("nan", "100.00") is False
    assert amounts_match("nan", "nan") is False


def test_amounts_match_s66_con_infinity_no_lanza() -> None:
    """Documentado, no corregido (fuera del hallazgo de esta ronda, spec §0): dos lados
    literalmente "Infinity" SÍ cuentan como acierto (`Infinity == Infinity` es `True`, sin
    lanzar) -- riesgo teórico, no observable con datos reales de una factura confirmada, que nunca
    es infinita."""
    assert amounts_match("Infinity", "100.00") is False
    assert amounts_match("Infinity", "Infinity") is True

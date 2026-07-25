"""Tests de comportamiento S2.10: veredicto de la comparativa (spec docs/specs/S2.9-S2.10-*.md).

Criterios C6, C7, C10. Módulo puro (`ocr.comparison`): sin red, sin Postgres. Reutiliza el mismo
`build_extracted` que ya usan los tests de S2.3 para construir lecturas de prueba.
"""

from __future__ import annotations

from tests._ocr import OWN_CIF, build_extracted


def test_c6_la_lectura_realzada_con_mas_senales_validas_gana() -> None:
    """C6: más señales a favor (contraparte válida, cuadre OK, confianza alta) -> gana."""
    from ocr.comparison import compare_readings

    pobre = build_extracted(counterparty_cif=None)  # sin contraparte legible: menos señales
    buena = build_extracted()  # contraparte válida, cuadre OK, alta confianza

    verdict = compare_readings(pobre, buena, OWN_CIF)

    assert verdict.winner == "enhanced"
    assert verdict.enhanced_score > verdict.original_score


def test_c7_la_lectura_original_con_mas_senales_validas_gana() -> None:
    """C7: si la original tiene más señales válidas, gana ella (nunca la realzada por defecto)."""
    from ocr.comparison import compare_readings

    buena = build_extracted()
    pobre = build_extracted(counterparty_cif=None)

    verdict = compare_readings(buena, pobre, OWN_CIF)

    assert verdict.winner == "original"
    assert verdict.original_score > verdict.enhanced_score


def test_c7_empate_exacto_da_tie_nunca_un_ganador_arbitrario() -> None:
    """C7/C10: misma puntuación exacta -> `tie`, nunca `original` ni `enhanced` por desempate."""
    from ocr.comparison import compare_readings

    misma_lectura = build_extracted()

    verdict = compare_readings(misma_lectura, misma_lectura, OWN_CIF)

    assert verdict.winner == "tie"
    assert verdict.original_score == verdict.enhanced_score


def test_c10_dos_lecturas_igual_de_pobres_tambien_empatan() -> None:
    """C10 (anti-alucinación): un empate en pobreza no se convierte en un ganador inventado."""
    from ocr.comparison import compare_readings

    pobre_a = build_extracted(counterparty_cif=None)
    pobre_b = build_extracted(counterparty_cif=None)

    verdict = compare_readings(pobre_a, pobre_b, OWN_CIF)

    assert verdict.winner == "tie"

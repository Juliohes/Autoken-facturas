"""Pruebas puras del cálculo del informe de carga R-050."""

from __future__ import annotations

from scripts.r050_load_test import _percentile

from shared.metrics import is_provider_rate_limited


def test_percentile_usa_interpolacion_lineal_y_no_redondea_la_muestra() -> None:
    assert _percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert _percentile([1.0, 2.0, 3.0, 4.0], 95) == 3.85


def test_rate_limit_del_proveedor_se_detecta_sin_guardar_el_error_crudo() -> None:
    assert is_provider_rate_limited(RuntimeError("provider returned HTTP 429"))
    assert is_provider_rate_limited(RuntimeError("resource_exhausted"))
    assert not is_provider_rate_limited(RuntimeError("timeout"))

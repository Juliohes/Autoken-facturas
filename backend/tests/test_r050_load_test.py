"""Pruebas puras del cálculo del informe de carga R-050."""

from __future__ import annotations

import pytest
from scripts.r050_load_test import (
    LoadConfig,
    _metrics,
    _percentile,
    _recovery_delta,
    _recovery_snapshot,
)

from shared.metrics import is_provider_rate_limited


def test_percentile_usa_interpolacion_lineal_y_no_redondea_la_muestra() -> None:
    assert _percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.5
    assert _percentile([1.0, 2.0, 3.0, 4.0], 95) == 3.85


def test_rate_limit_del_proveedor_se_detecta_sin_guardar_el_error_crudo() -> None:
    assert is_provider_rate_limited(RuntimeError("provider returned HTTP 429"))
    assert is_provider_rate_limited(RuntimeError("resource_exhausted"))
    assert not is_provider_rate_limited(RuntimeError("timeout"))


def test_informe_r050_separa_el_estado_de_recuperacion_sin_datos_de_negocio() -> None:
    metrics = {
        "autoken_ocr_queue_backend_up": 1.0,
        "autoken_ocr_queue_depth": 3.0,
        'autoken_ocr_documents{state="pending"}': 2.0,
        'autoken_ocr_documents{state="processing"}': 1.0,
        'autoken_ocr_documents{state="abandoned"}': 0.0,
        'autoken_ocr_documents{state="failed"}': 0.0,
        "autoken_expired_pending_count": 4.0,
    }

    assert _recovery_snapshot(metrics) == {
        "queue_backend_up": 1.0,
        "queue_depth": 3.0,
        "pending": 2.0,
        "processing": 1.0,
        "abandoned": 0.0,
        "failed": 0.0,
        "expired_pending": 4.0,
    }


def test_informe_r050_compara_metricas_globales_con_la_linea_base() -> None:
    before = {
        "autoken_ocr_queue_backend_up": 1.0,
        "autoken_ocr_queue_depth": 2.0,
        'autoken_ocr_documents{state="pending"}': 1.0,
        'autoken_ocr_documents{state="processing"}': 0.0,
        'autoken_ocr_documents{state="abandoned"}': 0.0,
        'autoken_ocr_documents{state="failed"}': 1.0,
        "autoken_expired_pending_count": 3.0,
    }
    after = {
        **before,
        "autoken_ocr_queue_depth": 0.0,
        'autoken_ocr_documents{state="pending"}': 0.0,
        'autoken_ocr_documents{state="failed"}': 1.0,
    }

    assert _recovery_delta(before, after) == {
        "queue_backend_up": 0.0,
        "queue_depth": -2.0,
        "pending": -1.0,
        "processing": 0.0,
        "abandoned": 0.0,
        "failed": 0.0,
        "expired_pending": 0.0,
    }


@pytest.mark.asyncio
async def test_informe_r050_conserva_metricas_agregadas_de_fases_de_upload() -> None:
    class Response:
        status_code = 200
        text = (
            "# HELP autoken_upload_phase_seconds_count count\n"
            'autoken_upload_phase_seconds_count{phase="deduplication"} 100.0\n'
            'autoken_upload_phase_seconds_sum{phase="deduplication"} 57.6\n'
        )

    class Client:
        async def get(self, _url: str) -> Response:
            return Response()

    metrics = await _metrics(Client(), LoadConfig("http://test", "load.test", ()))

    assert metrics['autoken_upload_phase_seconds_count{phase="deduplication"}'] == 100.0
    assert metrics['autoken_upload_phase_seconds_sum{phase="deduplication"}'] == 57.6

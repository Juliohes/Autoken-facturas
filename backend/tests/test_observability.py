"""Tests de comportamiento S5.6: captura de errores (Sentry) y métricas Prometheus.

Spec: docs/specs/S5.6-monitorizacion-y-alertas.md, criterios C1-C6. C1/C2 verifican el arranque de
la app (sin red real a Sentry, con un doble de `sentry_sdk.init`). C3-C6 verifican `GET /metrics`
contra Redis real, encolando trabajos con el mismo mecanismo real que usa la API
(`arq.create_pool`).
"""

from __future__ import annotations

import os
import re
from uuid import uuid4

import httpx
import pytest

Api = tuple[httpx.AsyncClient, dict[str, str]]

_METRICS = "/api/v1/metrics"


@pytest.fixture(autouse=True)
def _reset_ocr_queue_health_cache() -> None:
    """`jobs.monitoring.ocr_queue_health` cachea con TTL (auditoría de seguridad, hallazgo alto):
    sin este reset, un caso podría ver el resultado cacheado por el caso anterior en vez del
    estado real de SU propia cola (`authapi` limpia Redis/Postgres por test, pero no este caché de
    proceso, que vive fuera de ambos)."""
    from jobs.monitoring import reset_cache

    reset_cache()


def _clear_settings_cache() -> None:
    from shared import config

    config.get_settings.cache_clear()


def _metric_value(body: str, name: str) -> float | None:
    """Extrae el valor numérico de una métrica de texto Prometheus por su nombre; `None` si
    falta."""
    match = re.search(rf"^{re.escape(name)} ([\d.eE+-]+)$", body, re.MULTILINE)
    return float(match.group(1)) if match else None


async def test_c1_sin_dsn_sentry_no_se_inicializa(monkeypatch: pytest.MonkeyPatch) -> None:
    """C1: sin SENTRY_DSN, `sentry_sdk.init` nunca se llama al construir la app."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kwargs: calls.append(kwargs))
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    _clear_settings_cache()
    try:
        from main import create_app

        create_app()
        assert calls == []
    finally:
        _clear_settings_cache()


async def test_c2_con_dsn_sentry_se_inicializa_con_ese_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    """C2: con SENTRY_DSN, `sentry_sdk.init` se llama una vez con ese DSN y el entorno de la app."""
    calls: list[dict[str, object]] = []
    monkeypatch.setattr("sentry_sdk.init", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setenv("SENTRY_DSN", "https://examplePublicKey@o0.ingest.sentry.io/0")
    _clear_settings_cache()
    try:
        from main import create_app

        create_app()
        assert len(calls) == 1
        assert calls[0]["dsn"] == "https://examplePublicKey@o0.ingest.sentry.io/0"
        assert calls[0]["environment"]  # entorno de la app, no vacío
        # Auditoría de seguridad: explícito, no heredado de un default del SDK que pudiera cambiar
        # (app fiscal multi-tenant, con contenido de facturas y credenciales en /auth/*).
        assert calls[0]["send_default_pii"] is False
        assert calls[0]["max_request_body_size"] == "never"
    finally:
        _clear_settings_cache()


async def test_metodo_http_desconocido_no_crea_una_serie_nueva(authapi: Api) -> None:
    """Regresión (auditoría de seguridad, hallazgo alto): un método HTTP arbitrario no crea una
    serie de Prometheus por sí mismo (cardinalidad sin límite, DoS de memoria); se agrupa en
    "OTHER"."""
    client, _dsns = authapi

    await client.request("UNMETODOINVENTADO123", _METRICS)
    resp = await client.get(_METRICS)

    assert 'method="UNMETODOINVENTADO123"' not in resp.text
    assert 'method="OTHER"' in resp.text


async def test_c3_metrics_expone_formato_prometheus(authapi: Api) -> None:
    """C3: `GET /metrics` da texto Prometheus con el contador HTTP y la métrica de cola OCR."""
    client, _dsns = authapi

    resp = await client.get(_METRICS)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "autoken_http_requests_total" in resp.text
    assert "autoken_ocr_queue_depth" in resp.text


async def _enqueue_dummy_ocr_job(redis_url: str, queue_name: str) -> None:
    from arq import create_pool
    from arq.connections import RedisSettings

    pool = await create_pool(RedisSettings.from_dsn(redis_url))
    try:
        await pool.enqueue_job("noop", _queue_name=queue_name, _job_id=str(uuid4()))
    finally:
        await pool.aclose()


async def test_c4_profundidad_de_cola_refleja_los_pendientes(authapi: Api) -> None:
    """C4: N trabajos encolados y ninguno consumido -> `autoken_ocr_queue_depth` vale N."""
    pytest.importorskip("arq")
    from shared.config import get_settings

    client, _dsns = authapi
    redis_url = os.environ["REDIS_URL"]
    queue_name = get_settings().ocr_queue_name

    for _ in range(3):
        await _enqueue_dummy_ocr_job(redis_url, queue_name)

    resp = await client.get(_METRICS)

    assert _metric_value(resp.text, "autoken_ocr_queue_depth") == 3.0


async def test_c5_antiguedad_del_mas_viejo_refleja_el_tiempo_real(authapi: Api) -> None:
    """C5: la antigüedad reportada es la del trabajo pendiente MÁS VIEJO, no del más reciente."""
    import asyncio

    pytest.importorskip("arq")
    from shared.config import get_settings

    client, _dsns = authapi
    redis_url = os.environ["REDIS_URL"]
    queue_name = get_settings().ocr_queue_name

    await _enqueue_dummy_ocr_job(redis_url, queue_name)  # el más viejo
    await asyncio.sleep(1.1)
    await _enqueue_dummy_ocr_job(redis_url, queue_name)  # recién encolado

    resp = await client.get(_METRICS)

    age = _metric_value(resp.text, "autoken_ocr_queue_oldest_pending_seconds")
    assert age is not None
    assert age >= 1.0  # refleja al más viejo (>=1.1s), no al recién encolado (~0s)


async def test_c6_cola_vacia_no_publica_antiguedad(authapi: Api) -> None:
    """C6: sin trabajos pendientes, profundidad 0 y SIN serie de antigüedad (no un `0`
    inventado)."""
    pytest.importorskip("arq")

    client, _dsns = authapi

    resp = await client.get(_METRICS)

    assert _metric_value(resp.text, "autoken_ocr_queue_depth") == 0.0
    assert "autoken_ocr_queue_oldest_pending_seconds" not in resp.text

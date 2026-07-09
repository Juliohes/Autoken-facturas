"""Tests del middleware de cabeceras de seguridad (endurecimiento S1.6 Parte B).

Verifican que toda respuesta lleva el conjunto conservador de cabeceras de seguridad y que
`Strict-Transport-Security` se emite SOLO en producción (tras TLS), no en desarrollo/HTTP.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import httpx
import pytest

_HEALTH = "/api/v1/health"
_ME = "/api/v1/auth/me"  # ruta protegida: sin token da 401 antes de tocar la BD


async def test_cabeceras_de_seguridad_en_todas_las_respuestas(
    client: httpx.AsyncClient,
) -> None:
    """La respuesta de un endpoint público lleva las cabeceras de seguridad base (sin HSTS)."""
    resp = await client.get(_HEALTH)
    assert resp.status_code == 200
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "no-referrer"
    csp = resp.headers["content-security-policy"]
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    # En desarrollo (HTTP) NO se anuncia HSTS: solo tiene sentido en producción tras TLS.
    assert "strict-transport-security" not in resp.headers


async def test_cabeceras_de_seguridad_tambien_en_respuestas_de_error(
    client: httpx.AsyncClient,
) -> None:
    """Las cabeceras de seguridad también viajan en una respuesta de error (401 sin token)."""
    resp = await client.get(_ME)
    assert resp.status_code == 401
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in resp.headers["content-security-policy"]


@pytest.fixture
async def prod_client() -> AsyncIterator[httpx.AsyncClient]:
    """Cliente contra una app construida con `app_env=production` (JWT secret válido)."""
    from shared import config

    prev_env = os.environ.get("APP_ENV")
    prev_secret = os.environ.get("JWT_SECRET")
    os.environ["APP_ENV"] = "production"
    os.environ["JWT_SECRET"] = "x" * 40  # >= 32 bytes: válido en producción
    config.get_settings.cache_clear()
    try:
        from main import create_app

        transport = httpx.ASGITransport(app=create_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        for var, prev in (("APP_ENV", prev_env), ("JWT_SECRET", prev_secret)):
            if prev is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = prev
        config.get_settings.cache_clear()


async def test_hsts_solo_en_produccion(prod_client: httpx.AsyncClient) -> None:
    """En producción se anuncia HSTS (max-age largo con subdominios) junto al resto de cabeceras."""
    resp = await prod_client.get(_HEALTH)
    assert resp.status_code == 200
    hsts = resp.headers["strict-transport-security"]
    assert hsts.startswith("max-age=")
    assert "includeSubDomains" in hsts
    # el resto de cabeceras base siguen presentes
    assert resp.headers["x-content-type-options"] == "nosniff"

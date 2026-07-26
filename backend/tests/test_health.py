"""Tests del endpoint de healthcheck (tarea 0.4)."""

from collections.abc import Iterator

import httpx
import pytest

from main import app
from shared.config import AppEnv, Settings, get_settings


async def test_health_ok(client: httpx.AsyncClient) -> None:
    """El healthcheck responde 200 con el estado esperado."""
    resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["service"]
    assert body["version"]
    assert body["environment"] in {"development", "staging", "production"}


async def test_health_sets_correlation_id(client: httpx.AsyncClient) -> None:
    """Toda respuesta incluye el header de correlación."""
    resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    assert resp.headers.get("X-Correlation-ID")


async def test_health_respects_incoming_correlation_id(client: httpx.AsyncClient) -> None:
    """Si la petición trae correlation id, se reutiliza en la respuesta."""
    cid = "test-correlation-123"
    resp = await client.get("/api/v1/health", headers={"X-Correlation-ID": cid})

    assert resp.status_code == 200
    assert resp.headers["X-Correlation-ID"] == cid


async def test_unknown_route_404(client: httpx.AsyncClient) -> None:
    """Una ruta inexistente devuelve 404."""
    resp = await client.get("/api/v1/does-not-exist")

    assert resp.status_code == 404


@pytest.fixture
def override_settings() -> Iterator[None]:
    """Sustituye `get_settings` por una configuración de prueba y limpia al terminar.

    BP-3: si el handler resolviera `get_settings()` por su cuenta (service locator), este
    override no tendría efecto. La app es un singleton de módulo, así que se limpia siempre.
    """
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_name="Servicio de prueba",
        app_version="9.9.9",
        app_env=AppEnv.PRODUCTION,
        # En producción el guard rechaza un `jwt_secret`/`db_encryption_master_key` default o
        # corto; este test comprueba el reflejo de settings, no los secretos, así que basta con
        # valores fuertes válidos.
        jwt_secret="prueba-secreto-jwt-fuerte-de-produccion-32b+",
        db_encryption_master_key="prueba-clave-cifrado-fuerte-de-produccion-32b+",
    )
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_settings, None)


async def test_health_refleja_settings_inyectados(
    client: httpx.AsyncClient, override_settings: None
) -> None:
    """BP-3 (C1): el endpoint refleja la `Settings` inyectada vía `dependency_overrides`."""
    resp = await client.get("/api/v1/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "Servicio de prueba"
    assert body["version"] == "9.9.9"
    assert body["environment"] == "production"

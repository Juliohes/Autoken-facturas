"""Tests del endpoint de healthcheck (tarea 0.4)."""

import httpx


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

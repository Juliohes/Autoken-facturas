"""Tests de los issues de seguimiento del Sprint 2.

- #66: el `RequestSizeLimitMiddleware` rechaza con 413 un cuerpo cuyo `Content-Length` supera el
  máximo, ANTES de tocar el cuerpo/auth/enrutado (guardarraíl anti-DoS de disco).
- #67: el cliente MinIO y el backend de antivirus se memoizan por configuración (no se reconstruyen
  en cada operación).
"""

from __future__ import annotations

from typing import Any

from invoice_intake import scanner, storage
from shared.middleware import RequestSizeLimitMiddleware


# --- #66: cota del cuerpo de la petición ---------------------------------------------------------
async def test_c66_content_length_excesivo_devuelve_413_sin_llamar_a_la_app() -> None:
    """Content-Length > máximo -> 413 desde el middleware; la app envuelta NO se invoca."""
    called: list[str] = []

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ARG001
        called.append("app")

    mw = RequestSizeLimitMiddleware(inner_app, max_body_bytes=10)
    scope = {"type": "http", "headers": [(b"content-length", b"11")]}
    messages: list[dict] = []

    async def send(message: dict) -> None:
        messages.append(message)

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    await mw(scope, receive, send)

    assert called == []  # el cuerpo gigante no llega a la app (ni a auth ni al volcado a disco)
    start = next(m for m in messages if m["type"] == "http.response.start")
    assert start["status"] == 413


async def test_c66_content_length_dentro_del_limite_pasa_a_la_app() -> None:
    """Content-Length <= máximo -> la petición pasa a la app envuelta."""
    called: list[str] = []

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ARG001
        called.append("app")

    mw = RequestSizeLimitMiddleware(inner_app, max_body_bytes=10)
    scope = {"type": "http", "headers": [(b"content-length", b"5")]}

    async def send(message: dict) -> None:  # pragma: no cover - la app dummy no envía
        pass

    async def receive() -> dict:  # pragma: no cover
        return {"type": "http.request", "body": b"", "more_body": False}

    await mw(scope, receive, send)

    assert called == ["app"]


# --- #67: memoización del cliente MinIO y del scanner --------------------------------------------
def test_c67_cliente_minio_memoizado() -> None:
    """`storage._client()` reutiliza el mismo cliente MinIO entre llamadas (misma config)."""
    assert storage._client() is storage._client()


def test_c67_scanner_memoizado() -> None:
    """`scanner._select_scanner()` reutiliza el mismo backend entre llamadas (misma config)."""
    assert scanner._select_scanner() is scanner._select_scanner()

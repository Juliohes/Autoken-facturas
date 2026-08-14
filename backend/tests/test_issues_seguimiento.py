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
    # S5.1 C2 ("toda respuesta"): este middleware responde sin pasar por
    # `SecurityHeadersMiddleware`, así que debe llevar las mismas cabeceras él mismo.
    headers = dict(start["headers"])
    assert headers[b"cross-origin-opener-policy"] == b"same-origin"
    assert headers[b"x-content-type-options"] == b"nosniff"


async def test_c66_content_length_dentro_del_limite_pasa_a_la_app() -> None:
    """Content-Length fiable dentro del máximo se entrega sin prelectura ni buffer."""
    events: list[str] = []

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ARG001
        events.append("app")
        assert await receive() == {"type": "http.request", "body": b"12345", "more_body": False}

    mw = RequestSizeLimitMiddleware(inner_app, max_body_bytes=10)
    scope = {"type": "http", "headers": [(b"content-length", b"5")]}

    async def send(message: dict) -> None:  # pragma: no cover - la app dummy no envía
        pass

    async def receive() -> dict:
        events.append("receive")
        return {"type": "http.request", "body": b"12345", "more_body": False}

    await mw(scope, receive, send)

    assert events == ["app", "receive"]


async def test_c66_cuerpo_chunked_excesivo_devuelve_413_antes_de_la_app() -> None:
    """El fragmento que cruza la cota no llega nunca a la app que ya recibía el stream."""
    called: list[str] = []
    received: list[bytes] = []

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ARG001
        called.append("app")
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            received.append(message.get("body", b""))

    mw = RequestSizeLimitMiddleware(inner_app, max_body_bytes=10)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/uploads",
        "headers": [(b"transfer-encoding", b"chunked")],
    }
    incoming = iter(
        [
            {"type": "http.request", "body": b"123456", "more_body": True},
            {"type": "http.request", "body": b"78901", "more_body": False},
        ]
    )
    messages: list[dict] = []

    async def receive() -> dict:
        return next(incoming)

    async def send(message: dict) -> None:
        messages.append(message)

    await mw(scope, receive, send)

    assert called == ["app"]
    assert received == [b"123456"]
    start = next(message for message in messages if message["type"] == "http.response.start")
    assert start["status"] == 413
    headers = dict(start["headers"])
    assert headers[b"cross-origin-opener-policy"] == b"same-origin"
    assert headers[b"x-content-type-options"] == b"nosniff"


async def test_c66_el_lote_admite_hasta_cinco_ficheros_individuales_y_sigue_acotado() -> None:
    """Solo `/uploads/batch` recibe la cota ampliada; las demás rutas quedan estrictas."""
    called: list[str] = []

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ARG001
        called.append("app")

    mw = RequestSizeLimitMiddleware(inner_app, max_body_bytes=10, max_batch_body_bytes=50)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/uploads/batch",
        "headers": [(b"content-length", b"50")],
    }

    async def send(message: dict) -> None:  # pragma: no cover - la app dummy no envía
        pass

    async def receive() -> dict:  # pragma: no cover
        return {"type": "http.request", "body": b"", "more_body": False}

    await mw(scope, receive, send)
    assert called == ["app"]


async def test_c66_lote_chunked_usa_la_cota_ampliada_y_reproduce_el_cuerpo() -> None:
    """El lote sin longitud declarada conserva su cota propia y llega por streaming."""
    received_body = bytearray()
    app_started = False

    async def inner_app(scope: Any, receive: Any, send: Any) -> None:  # noqa: ARG001
        nonlocal app_started
        app_started = True
        while True:
            message = await receive()
            assert app_started
            received_body.extend(message.get("body", b""))
            if not message.get("more_body", False):
                return

    mw = RequestSizeLimitMiddleware(inner_app, max_body_bytes=10, max_batch_body_bytes=50)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/uploads/batch",
        "headers": [(b"transfer-encoding", b"chunked")],
    }
    incoming = iter(
        [
            {"type": "http.request", "body": b"a" * 30, "more_body": True},
            {"type": "http.request", "body": b"b" * 20, "more_body": False},
        ]
    )

    async def receive() -> dict:
        return next(incoming)

    async def send(message: dict) -> None:  # pragma: no cover - la app dummy no responde
        pass

    await mw(scope, receive, send)

    assert bytes(received_body) == b"a" * 30 + b"b" * 20


# --- #67: memoización del cliente MinIO y del scanner --------------------------------------------
def test_c67_cliente_minio_memoizado() -> None:
    """`storage._client()` reutiliza el mismo cliente MinIO entre llamadas (misma config)."""
    assert storage._client() is storage._client()


def test_c67_scanner_memoizado() -> None:
    """`scanner._select_scanner()` reutiliza el mismo backend entre llamadas (misma config)."""
    assert scanner._select_scanner() is scanner._select_scanner()

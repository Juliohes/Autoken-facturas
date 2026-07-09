"""Middleware de cabeceras de seguridad (defensa en profundidad) — endurecimiento S1.6 Parte B.

Fija en TODAS las respuestas un conjunto conservador de cabeceras de seguridad apropiadas para una
API JSON (sin superficie HTML propia): evita sniffing de tipos, enmarcado (clickjacking), fuga del
referer y, como CSP mínima, prohíbe cargar cualquier recurso y ser enmarcado. `Strict-Transport-
Security` solo se emite en producción (detrás de TLS): anunciar HSTS sin HTTPS no aporta y en
desarrollo/HTTP es inútil o molesto.

Se monta con una sola línea en `main.py`; toda la política vive aquí (un único sitio, sin
dispersión). Nota: S5.1 afinará y medirá con Mozilla Observatory; esto deja una base sólida.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Cabeceras estáticas para una API JSON. CSP mínima: no se sirve ni HTML ni recursos propios, así
# que se prohíbe todo (`default-src 'none'`) y ser enmarcado (`frame-ancestors 'none'`).
_STATIC_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
# HSTS de 2 años con subdominios (solo producción, tras TLS). Sin `preload` para no comprometerse
# con la lista de precarga desde aquí (decisión de despliegue; se puede añadir en S5.1).
_HSTS_VALUE = "max-age=63072000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Añade cabeceras de seguridad a cada respuesta; HSTS solo si `hsts=True` (producción)."""

    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        # `setdefault`: no se pisa una cabecera que un endpoint concreto haya fijado a propósito.
        for name, value in _STATIC_SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if self._hsts:
            response.headers.setdefault("Strict-Transport-Security", _HSTS_VALUE)
        return response

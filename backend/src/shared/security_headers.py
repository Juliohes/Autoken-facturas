"""Middleware de cabeceras de seguridad (defensa en profundidad) — endurecimiento S1.6 Parte B.

Fija en TODAS las respuestas un conjunto conservador de cabeceras de seguridad apropiadas para una
API JSON: evita sniffing de tipos, enmarcado (clickjacking), fuga del referer y, como CSP mínima,
prohíbe cargar cualquier recurso y ser enmarcado. `Strict-Transport-Security` solo se emite en
producción (detrás de TLS): anunciar HSTS sin HTTPS no aporta y en desarrollo/HTTP es inútil o
molesto.

Nota (S4.3): desde que `GET /manifest.webmanifest` sirve el Web App Manifest, esta API ya tiene un
consumidor que no es un cliente JS de la SPA (el propio navegador, vía `<link rel="manifest">`). No
cambia la política: la CSP que rige si el navegador puede *cargar* el manifest es la del documento
HTML que lo enlaza, no esta cabecera de la respuesta del manifest en sí.

Se monta con una sola línea en `main.py`; toda la política vive aquí (un único sitio, sin
dispersión).

S5.1: añade `Cross-Origin-Opener-Policy`/`Cross-Origin-Resource-Policy` (`same-origin`), mitigación
de clase Spectre/XS-Leaks gratis en una API que no necesita ser embebida ni abierta como ventana
relacionada desde otro origen. El escaneo real con Mozilla Observatory queda pendiente de un
despliegue público (no hay ninguno accesible desde este entorno de trabajo, spec S5.1 §6); este
módulo cubre el checklist de cabeceras que Observatory puntúa para una API JSON.

`apply_static_security_headers` se expone aparte (auditoría S5.1, hallazgo de patrones+seguridad):
`RequestSizeLimitMiddleware` responde un `413` sin llamar al resto de la cadena (es el middleware
más externo, a propósito, para no tocar el cuerpo antes de medirlo) y por eso nunca pasaba por
`SecurityHeadersMiddleware`. Reutiliza el mismo conjunto de cabeceras en su respuesta en vez de
duplicarlo, para que "toda respuesta" (C2) sea cierto también en ese camino.
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
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
# HSTS de 2 años con subdominios (solo producción, tras TLS). Sin `preload` para no comprometerse
# con la lista de precarga desde aquí (decisión de despliegue; se puede añadir en S5.1).
_HSTS_VALUE = "max-age=63072000; includeSubDomains"


def apply_static_security_headers(response: Response) -> None:
    """Fija el conjunto estático de cabeceras (sin HSTS) en `response`, sin pisar una ya fijada."""
    for name, value in _STATIC_SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)


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
        apply_static_security_headers(response)
        if self._hsts:
            response.headers.setdefault("Strict-Transport-Security", _HSTS_VALUE)
        return response

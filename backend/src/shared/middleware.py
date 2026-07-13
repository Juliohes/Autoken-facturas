"""Middleware transversal: correlación por petición y resolución subdominio->tenant."""

import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from tenancy.resolution import (
    ResolvedTenant,
    extract_subdomain,
    is_platform_host,
    resolve_tenant,
)
from tenancy.resolution_cache import NegativeTenantResolutionCache

CORRELATION_ID_HEADER = "X-Correlation-ID"


class RequestSizeLimitMiddleware:
    """Rechaza con 413 una petición cuyo `Content-Length` supera el máximo, antes de leer el cuerpo.

    Guardarraíl anti-DoS de disco (issue #66): Starlette/python-multipart vuelca el cuerpo a un
    fichero temporal durante el parseo, así que comprobar el `Content-Length` en el borde (antes de
    tocar el cuerpo, la auth o el enrutado) evita materializar un cuerpo gigante. Un cliente sin
    `Content-Length` (chunked) no se caza aquí: el endpoint de subida sigue acotando los bytes
    leídos en memoria (S2.1 C5) y el proxy inverso debe poner su propia cota en producción. Es ASGI
    puro (no `BaseHTTPMiddleware`) para responder sin instanciar la petición ni su cuerpo.
    """

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self._app = app
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            declared = Headers(scope=scope).get("content-length")
            if declared is not None and declared.isdigit() and int(declared) > self._max_body_bytes:
                response = PlainTextResponse(
                    f"El cuerpo de la petición supera el máximo ({self._max_body_bytes} bytes)",
                    status_code=413,
                )
                await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


async def _resolve_uncached(slug: str) -> ResolvedTenant | None:
    """Resolver base de la caché: delega en `resolve_tenant` buscándolo en el namespace del módulo.

    Indirección deliberada para que la caché use SIEMPRE el `resolve_tenant` actual de este módulo
    (los tests lo sustituyen con `monkeypatch.setattr('shared.middleware.resolve_tenant', ...)`);
    capturar la referencia en el constructor de la caché lo dejaría fijado y rompería ese seam.
    """
    return await resolve_tenant(slug)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Asigna (o respeta) un correlation id y lo enlaza al contexto de logs.

    Si la petición trae el header `X-Correlation-ID`, se reutiliza; si no, se
    genera uno nuevo. El id se devuelve en la respuesta y queda disponible en
    todos los logs estructurados de la petición.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response


class TenantResolutionMiddleware(BaseHTTPMiddleware):
    """Resuelve el subdominio del `Host` a su tenant y lo deja en `request.state.tenant`.

    `request.state.tenant` queda a `None` si el host es raíz/plataforma o si el subdominio no
    corresponde a ningún tenant activo (indistinguible: no se enumera). No fuerza 404 por sí mismo;
    los endpoints que requieren tenant deciden (p. ej. `/tenants/current` da 404 si es `None`).
    """

    def __init__(
        self,
        app: ASGIApp,
        base_domain: str,
        *,
        allow_localhost: bool = False,
        cache_ttl_seconds: float = 30,
        cache_max_size: int = 1024,
    ) -> None:
        super().__init__(app)
        self._base_domain = base_domain
        self._allow_localhost = allow_localhost
        # Adaptador de caché (cota LRU + TTL) sobre la resolución; solo memoriza negativos (#52).
        self._cache = NegativeTenantResolutionCache(
            _resolve_uncached, ttl_seconds=cache_ttl_seconds, max_size=cache_max_size
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host = request.headers.get("host", "")
        slug = extract_subdomain(host, self._base_domain, allow_localhost=self._allow_localhost)
        request.state.tenant = await self._cache.resolve(slug) if slug is not None else None
        # El host de plataforma (panel) es el único donde entra un `platform_admin` (S1.6 C8).
        request.state.is_platform_host = is_platform_host(
            host, self._base_domain, allow_localhost=self._allow_localhost
        )
        return await call_next(request)

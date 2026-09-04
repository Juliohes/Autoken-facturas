"""Middleware transversal: correlación por petición y resolución subdominio->tenant."""

import uuid
from collections.abc import Awaitable, Callable
from time import perf_counter

import structlog
from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from shared.metrics import http_requests_total, normalize_http_method, upload_to_201_seconds
from shared.security_headers import apply_static_security_headers
from tenancy.resolution import (
    ResolvedTenant,
    extract_subdomain,
    is_platform_host,
    is_root_or_reserved_host,
    resolve_tenant,
    resolve_tenant_by_custom_domain,
)
from tenancy.resolution_cache import NegativeTenantResolutionCache

CORRELATION_ID_HEADER = "X-Correlation-ID"


class RequestSizeLimitMiddleware:
    """Rechaza con 413 una petición cuyo cuerpo supera el máximo, antes del parser multipart.

    Guardarraíl anti-DoS de disco (issue #66): Starlette/python-multipart vuelca el cuerpo a un
    fichero temporal durante el parseo. Con `Content-Length`, se rechaza sin leer ningún byte si
    rebasa la cota y, si cabe, se deja fluir directamente al parser. Sin esa cabecera (o si es
    inválida), envuelve `receive`: cuenta cada fragmento y responde 413 antes de entregar el que
    rebasa la cota. Así no acumula el cuerpo en memoria ni permite que el parser escriba el exceso.
    Es ASGI puro (no `BaseHTTPMiddleware`) para responder sin instanciar una petición.
    """

    def __init__(
        self, app: ASGIApp, *, max_body_bytes: int, max_batch_body_bytes: int | None = None
    ) -> None:
        self._app = app
        self._max_body_bytes = max_body_bytes
        self._max_batch_body_bytes = max_batch_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        declared = Headers(scope=scope).get("content-length")
        is_batch_upload = scope.get("method") == "POST" and scope.get("path", "").endswith(
            "/uploads/batch"
        )
        max_body_bytes = (
            self._max_batch_body_bytes
            if is_batch_upload and self._max_batch_body_bytes is not None
            else self._max_body_bytes
        )
        if declared is not None and declared.isdigit() and int(declared) > max_body_bytes:
            await self._send_too_large(scope, receive, send, max_body_bytes)
            return

        received_bytes = 0
        rejected = False

        async def limited_receive() -> Message:
            nonlocal received_bytes, rejected
            message = await receive()
            if message["type"] != "http.request":
                return message
            received_bytes += len(message.get("body", b""))
            if received_bytes > max_body_bytes:
                rejected = True
                await self._send_too_large(scope, receive, send, max_body_bytes)
                # La aplicación ya puede estar leyendo fragmentos previos. No ve el fragmento que
                # excede ni llega a emitir una respuesta posterior que tape el 413.
                return {"type": "http.disconnect"}
            return message

        async def limited_send(message: Message) -> None:
            if not rejected:
                await send(message)

        await self._app(scope, limited_receive, limited_send)

    @staticmethod
    async def _send_too_large(
        scope: Scope, receive: Receive, send: Send, max_body_bytes: int
    ) -> None:
        response = PlainTextResponse(
            f"El cuerpo de la petición supera el máximo ({max_body_bytes} bytes)", status_code=413
        )
        # Este middleware es el más externo (a propósito, ver docstring): responde SIN llamar a la
        # aplicación, así que `SecurityHeadersMiddleware` nunca se ejecuta para este camino.
        apply_static_security_headers(response)
        await response(scope, receive, send)


async def _resolve_uncached(slug: str) -> ResolvedTenant | None:
    """Resolver base de la caché: delega en `resolve_tenant` buscándolo en el namespace del módulo.

    Indirección deliberada para que la caché use SIEMPRE el `resolve_tenant` actual de este módulo
    (los tests lo sustituyen con `monkeypatch.setattr('shared.middleware.resolve_tenant', ...)`);
    capturar la referencia en el constructor de la caché lo dejaría fijado y rompería ese seam.
    """
    return await resolve_tenant(slug)


async def _resolve_custom_domain_uncached(host: str) -> ResolvedTenant | None:
    """Resolver base de la caché de dominios propios (S4.6): misma indirección que
    `_resolve_uncached`, para el mismo seam de test
    (`shared.middleware.resolve_tenant_by_custom_domain`).
    """
    return await resolve_tenant_by_custom_domain(host)


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


class MetricsMiddleware(BaseHTTPMiddleware):
    """Cuenta cada petición HTTP por método y código de estado (S5.6,
    `autoken_http_requests_total`).

    Solo esas dos dimensiones, a propósito: NUNCA la ruta. Etiquetar por `request.url.path` crearía
    una serie de Prometheus distinta por cada URL con un identificador variable (facturas, tenants,
    IDs de fichero...) — cardinalidad sin límite y, más grave, el nombre de la métrica podría acabar
    filtrando identificadores de negocio de un tenant. El método se normaliza contra una lista
    conocida (`normalize_http_method`) por el mismo motivo de cardinalidad: un cliente puede mandar
    cualquier token como método HTTP.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = perf_counter()
        response = await call_next(request)
        method = normalize_http_method(request.method)
        http_requests_total.labels(method=method, status=str(response.status_code)).inc()
        if (
            request.method == "POST"
            and request.url.path == "/api/v1/uploads"
            and response.status_code == 201
        ):
            upload_to_201_seconds.observe(perf_counter() - started)
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
        # Misma protección para el fallback por dominio propio (S4.6): sin caché, un `Host`
        # arbitrario (el atacante lo controla al 100%, a diferencia del subdominio, que ya lo
        # protegía #52) generaría una consulta a Postgres nueva por petición sin límite —
        # hallazgo de la auditoría de seguridad, corregido antes de mergear.
        self._custom_domain_cache = NegativeTenantResolutionCache(
            _resolve_custom_domain_uncached, ttl_seconds=cache_ttl_seconds, max_size=cache_max_size
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        host = request.headers.get("host", "")
        slug = extract_subdomain(host, self._base_domain, allow_localhost=self._allow_localhost)
        tenant = await self._cache.resolve(slug) if slug is not None else None
        if tenant is None and not is_root_or_reserved_host(
            host, self._base_domain, allow_localhost=self._allow_localhost
        ):
            # El guard de arriba evita el round-trip extra en cada petición al panel de
            # plataforma (host reservado, nunca puede ser un dominio propio de cliente); la
            # caché (mismo patrón que el subdominio, #52) evita que un `Host` arbitrario
            # controlado por un atacante martillee Postgres sin límite.
            tenant = await self._custom_domain_cache.resolve(host)
        request.state.tenant = tenant
        # El host de plataforma (panel) es el único donde entra un `platform_admin` (S1.6 C8).
        request.state.is_platform_host = is_platform_host(
            host, self._base_domain, allow_localhost=self._allow_localhost
        )
        return await call_next(request)

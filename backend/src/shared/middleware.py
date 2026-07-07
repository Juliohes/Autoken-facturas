"""Middleware transversal: correlación por petición y resolución subdominio->tenant."""

import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from tenancy.resolution import extract_subdomain, resolve_tenant

CORRELATION_ID_HEADER = "X-Correlation-ID"


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

    def __init__(self, app: ASGIApp, base_domain: str, *, allow_localhost: bool = False) -> None:
        super().__init__(app)
        self._base_domain = base_domain
        self._allow_localhost = allow_localhost

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        slug = extract_subdomain(
            request.headers.get("host", ""),
            self._base_domain,
            allow_localhost=self._allow_localhost,
        )
        request.state.tenant = await resolve_tenant(slug) if slug is not None else None
        return await call_next(request)

"""Punto de entrada de la API de Autoken Facturas v2.

Crea la aplicación FastAPI, configura logging estructurado y middleware de
correlación, y monta los routers bajo el prefijo de la API (`/api/v1`).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from companies.router import router as companies_router
from identity.registration_router import router as registration_router
from identity.router import router as auth_router
from invoice_intake.router import duplicate_upload_handler
from invoice_intake.router import router as intake_router
from invoice_intake.service import DuplicateUpload
from invoicing.router import invoices_router as invoicing_invoices_router
from invoicing.router import router as invoicing_router
from jobs.metrics_router import router as metrics_router
from platform_admin.benchmark_batch_router import router as platform_benchmark_batch_router
from platform_admin.benchmark_ranking_router import router as platform_benchmark_ranking_router
from platform_admin.health import router as health_router
from platform_admin.lab_router import router as platform_lab_router
from platform_admin.ranking_router import router as platform_ranking_router
from platform_admin.settings_router import router as platform_settings_router
from platform_admin.tenants_router import router as platform_tenants_router
from reporting.router import router as reporting_router
from shared.config import Settings, get_settings
from shared.db import dispose_engine, get_engine
from shared.db_security import assert_runtime_role_cannot_bypass_rls
from shared.error_tracking import init_sentry
from shared.logging import configure_logging, get_logger
from shared.middleware import (
    CorrelationIdMiddleware,
    MetricsMiddleware,
    RequestSizeLimitMiddleware,
    TenantResolutionMiddleware,
)
from shared.redis import dispose_redis
from shared.security_headers import SecurityHeadersMiddleware
from tenancy.router import router as tenancy_router


def create_app() -> FastAPI:
    """Construye y configura la aplicación FastAPI (application factory)."""
    settings: Settings = get_settings()
    configure_logging(settings.log_level)
    init_sentry(settings)  # no-op sin SENTRY_DSN (S5.6 C1/C2)
    log = get_logger("app")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        log.info("app_startup", env=settings.app_env.value, version=settings.app_version)
        if settings.is_production:
            # Guardarraíl de arranque (#50, ADR-0014): la app NO debe conectarse como superusuario
            # ni con BYPASSRLS, o la RLS se saltaría y caería el aislamiento multi-tenant. Solo en
            # producción, para no exigir conexión a BD en dev/test. Si falla, la app no levanta.
            await assert_runtime_role_cannot_bypass_rls(get_engine())
        yield
        await dispose_engine()  # cierra el pool de BD al parar (issue #50)
        await dispose_redis()  # cierra el cliente Redis al parar (S1.3)
        log.info("app_shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        TenantResolutionMiddleware,
        base_domain=settings.base_domain,
        allow_localhost=not settings.is_production,  # `*.localhost` solo fuera de producción
        cache_ttl_seconds=settings.subdomain_cache_ttl_seconds,
        cache_max_size=settings.subdomain_cache_max_size,
    )
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(MetricsMiddleware)  # cuenta cada petición por método+status (S5.6)
    # Cabeceras de seguridad en todas las respuestas (defensa en profundidad); HSTS solo en prod.
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
    # Cota del cuerpo de la petición (issue #66): el más externo, para rechazar (413) un cuerpo
    # gigante por `Content-Length` antes de auth, enrutado o volcado a disco del multipart.
    app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=settings.max_request_body_bytes)
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(metrics_router, prefix=settings.api_prefix)
    app.include_router(tenancy_router, prefix=settings.api_prefix)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(registration_router, prefix=settings.api_prefix)
    app.include_router(companies_router, prefix=settings.api_prefix)
    app.include_router(intake_router, prefix=settings.api_prefix)
    app.include_router(invoicing_router, prefix=settings.api_prefix)
    app.include_router(invoicing_invoices_router, prefix=settings.api_prefix)
    app.include_router(reporting_router, prefix=settings.api_prefix)
    app.include_router(platform_tenants_router, prefix=settings.api_prefix)
    app.include_router(platform_settings_router, prefix=settings.api_prefix)
    app.include_router(platform_ranking_router, prefix=settings.api_prefix)
    app.include_router(platform_lab_router, prefix=settings.api_prefix)
    app.include_router(platform_benchmark_batch_router, prefix=settings.api_prefix)
    app.include_router(platform_benchmark_ranking_router, prefix=settings.api_prefix)

    # Un duplicado de intake (S2.1 C8/C14) responde 409 con `duplicate_of`; se maneja a nivel de app
    # para que la excepción propague desde el endpoint y la dependencia deshaga antes la
    # transacción (rollback tras la carrera del UNIQUE) antes de emitir la respuesta.
    app.add_exception_handler(DuplicateUpload, duplicate_upload_handler)

    return app


app = create_app()

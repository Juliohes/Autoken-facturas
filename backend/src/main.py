"""Punto de entrada de la API de Autoken Facturas v2.

Crea la aplicación FastAPI, configura logging estructurado y middleware de
correlación, y monta los routers bajo el prefijo de la API (`/api/v1`).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from platform_admin.health import router as health_router
from shared.config import Settings, get_settings
from shared.logging import configure_logging, get_logger
from shared.middleware import CorrelationIdMiddleware


def create_app() -> FastAPI:
    """Construye y configura la aplicación FastAPI (application factory)."""
    settings: Settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("app")

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        log.info("app_startup", env=settings.app_env.value, version=settings.app_version)
        yield
        log.info("app_shutdown")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIdMiddleware)
    app.include_router(health_router, prefix=settings.api_prefix)

    return app


app = create_app()

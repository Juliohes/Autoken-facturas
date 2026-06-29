"""Endpoint de healthcheck del servicio.

Ubicado en `platform_admin` por ser de uso operativo/plataforma. No toca BD
en 0.4: solo confirma que el proceso está vivo y devuelve metadatos básicos.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from shared.config import Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Respuesta del healthcheck."""

    status: str
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Devuelve el estado del servicio (liveness).

    `Settings` se recibe por inyección de dependencias (DIP), no resolviéndola dentro del
    handler: así es sustituible en test vía `app.dependency_overrides` (BP-3).
    """
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
    )

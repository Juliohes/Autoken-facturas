"""Endpoints HTTP del interruptor admin-tech (S4.10): `GET`/`PUT /api/v1/platform/settings`.

Capa HTTP fina: autentica y autoriza (`require_admin_tech`, exige `platform_admin` + el flag
`is_admin_tech`, comprobado fresco en cada petición), tipa el body y delega en `settings_service`.
Un `platform_admin` sin el flag recibe 403 (mismo criterio de denegar por defecto que el resto de
`platform_admin`, spec S4.10 §3 C1/C3).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from identity.authz import require_admin_tech
from identity.dependencies import AdminTechAuthContext
from platform_admin import settings_service

router = APIRouter(prefix="/platform/settings", tags=["platform"])

AdminTech = Annotated[AdminTechAuthContext, Depends(require_admin_tech())]


class PlatformSettingsOut(BaseModel):
    ocr_experiment_enabled: bool


class PlatformSettingsIn(BaseModel):
    ocr_experiment_enabled: bool


@router.get("")
async def get_settings(identity: AdminTech) -> PlatformSettingsOut:
    settings = await settings_service.get_settings(identity.session)
    return PlatformSettingsOut(ocr_experiment_enabled=settings.ocr_experiment_enabled)


@router.put("")
async def set_settings(body: PlatformSettingsIn, identity: AdminTech) -> PlatformSettingsOut:
    settings = await settings_service.set_settings(
        identity.session, ocr_experiment_enabled=body.ocr_experiment_enabled
    )
    return PlatformSettingsOut(ocr_experiment_enabled=settings.ocr_experiment_enabled)

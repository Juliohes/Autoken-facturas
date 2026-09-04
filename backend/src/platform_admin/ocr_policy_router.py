"""Administración de la política OCR de producción R-033."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from identity.authz import require_admin_tech
from identity.dependencies import AdminTechAuthContext
from ocr.policy import OcrPolicy
from platform_admin import settings_service

router = APIRouter(prefix="/platform/ocr-policy", tags=["platform"])

AdminTech = Annotated[AdminTechAuthContext, Depends(require_admin_tech())]


@router.get("", response_model=OcrPolicy)
async def get_ocr_policy(identity: AdminTech) -> OcrPolicy:
    return await settings_service.get_ocr_policy(identity.session)


@router.put("", response_model=OcrPolicy)
async def set_ocr_policy(policy: OcrPolicy, identity: AdminTech) -> OcrPolicy:
    try:
        return await settings_service.set_ocr_policy(identity.session, policy)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

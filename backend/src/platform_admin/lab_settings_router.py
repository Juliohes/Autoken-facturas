"""Controles del laboratorio OCR y promoción explícita a producción (R-046)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from identity.authz import require_admin_tech
from identity.dependencies import AdminTechAuthContext
from ocr.policy import OcrPolicy
from platform_admin import settings_service
from platform_admin.settings_repository import OcrLabSettings

router = APIRouter(prefix="/platform/ocr-lab", tags=["platform"])

AdminTech = Annotated[AdminTechAuthContext, Depends(require_admin_tech())]


class OcrLabSettingsPayload(BaseModel):
    lab_visible: bool
    auto_benchmark_enabled: bool
    benchmark_engines: list[str] = Field(min_length=1)
    benchmark_variants: list[str] = Field(min_length=1)


class OcrLabSettingsOut(OcrLabSettingsPayload):
    pass


class OcrPolicyPromotionOut(BaseModel):
    id: UUID
    old_policy: OcrPolicy
    new_policy: OcrPolicy
    actor_id: UUID
    promoted_at: datetime


def _lab_out(settings: OcrLabSettings) -> OcrLabSettingsOut:
    return OcrLabSettingsOut(
        lab_visible=settings.lab_visible,
        auto_benchmark_enabled=settings.auto_benchmark_enabled,
        benchmark_engines=settings.benchmark_engines,
        benchmark_variants=settings.benchmark_variants,
    )


@router.get("/settings", response_model=OcrLabSettingsOut)
async def get_lab_settings(identity: AdminTech) -> OcrLabSettingsOut:
    return _lab_out(await settings_service.get_lab_settings(identity.session))


@router.put("/settings", response_model=OcrLabSettingsOut)
async def set_lab_settings(body: OcrLabSettingsPayload, identity: AdminTech) -> OcrLabSettingsOut:
    settings = await settings_service.set_lab_settings(
        identity.session,
        OcrLabSettings(
            lab_visible=body.lab_visible,
            auto_benchmark_enabled=body.auto_benchmark_enabled,
            benchmark_engines=body.benchmark_engines,
            benchmark_variants=body.benchmark_variants,
        ),
    )
    return _lab_out(settings)


@router.post("/promote", response_model=OcrPolicyPromotionOut)
async def promote_ocr_policy(body: OcrPolicy, identity: AdminTech) -> OcrPolicyPromotionOut:
    try:
        promotion = await settings_service.promote_ocr_policy(
            identity.session, actor_id=identity.user_id, policy=body
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OcrPolicyPromotionOut(
        id=promotion.id,
        old_policy=OcrPolicy.model_validate(promotion.old_policy),
        new_policy=OcrPolicy.model_validate(promotion.new_policy),
        actor_id=promotion.actor_id,
        promoted_at=promotion.promoted_at,
    )

"""Endpoints globales de supervisión admin-tech (R-027)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from identity.authz import require_admin_tech
from identity.dependencies import AdminTechAuthContext
from invoicing import service as invoicing_service
from platform_admin import supervision_service

router = APIRouter(prefix="/platform/pending", tags=["platform"])
AdminTech = Annotated[AdminTechAuthContext, Depends(require_admin_tech())]


class GlobalPendingOut(BaseModel):
    tenant_id: UUID
    tenant_slug: str
    id: UUID
    user_email: str
    company_name: str
    status: str
    created_at: datetime
    direction: Literal["recibida", "emitida"] | None
    page_count: int


class GlobalPendingPageOut(BaseModel):
    items: list[GlobalPendingOut]
    next_cursor: str | None


@router.get("")
async def list_global_pending(
    identity: AdminTech,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
) -> GlobalPendingPageOut:
    try:
        page = await supervision_service.list_pending(identity, cursor=cursor, limit=limit)
    except supervision_service.InvalidGlobalPendingCursor as exc:
        raise HTTPException(status_code=400, detail="Cursor inválido") from exc
    return GlobalPendingPageOut(
        items=[GlobalPendingOut(**item.__dict__) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{tenant_id}/{file_id}/review-readonly")
async def global_review_readonly(
    request: Request, identity: AdminTech, tenant_id: UUID, file_id: UUID
) -> dict[str, object]:
    try:
        tenant = await supervision_service.resolve_tenant(identity, tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant no encontrado")
        data = await supervision_service.open_readonly(
            identity,
            tenant_id=tenant_id,
            tenant_slug=tenant.slug,
            file_id=file_id,
            request_id=getattr(request.state, "correlation_id", None),
            source_ip=request.client.host if request.client else None,
        )
    except invoicing_service.InvoicingError as exc:
        raise HTTPException(status_code=404, detail="Documento no encontrado") from exc
    return {
        "fields": data.fields,
        "confidences": data.confidences,
        "counterparty_verdict": data.counterparty_verdict,
        "own": data.own,
        "warnings": data.warnings,
        "blocking_reasons": data.blocking_reasons,
        "direction": data.direction,
        "source": data.source,
        "draft_revision": data.draft_revision,
        "draft_updated_at": data.draft_updated_at,
        "page_count": data.page_count,
    }

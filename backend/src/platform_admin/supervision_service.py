"""Supervisión global explícita para admin-tech (R-027)."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from identity.dependencies import AdminTechAuthContext, AuthContext
from invoice_intake import repository as intake_repository
from invoicing import repository as invoicing_repository
from invoicing import service as invoicing_service
from platform_admin import repository as platform_repository
from shared.audit import write_audit
from shared.config import get_settings
from shared.db import tenant_session
from shared.encryption import tenant_encryption_key


@dataclass(frozen=True)
class GlobalPending:
    tenant_id: UUID
    tenant_slug: str
    id: UUID
    user_email: str
    company_name: str
    status: str
    created_at: datetime
    direction: str | None
    page_count: int


@dataclass(frozen=True)
class GlobalPendingPage:
    items: list[GlobalPending]
    next_cursor: str | None


class InvalidGlobalPendingCursor(ValueError):
    """El cursor global no tiene el formato compuesto esperado."""


def _encode_cursor(created_at: datetime, item_id: UUID) -> str:
    payload = json.dumps([created_at.isoformat(), str(item_id)], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_at_raw, item_id_raw = json.loads(base64.urlsafe_b64decode(padded).decode())
        created_at = datetime.fromisoformat(created_at_raw)
        if created_at.tzinfo is None:
            raise ValueError
        return created_at, UUID(item_id_raw)
    except (
        ValueError,
        TypeError,
        json.JSONDecodeError,
        UnicodeDecodeError,
        binascii.Error,
        KeyError,
    ) as exc:
        raise InvalidGlobalPendingCursor from exc


async def resolve_tenant(
    identity: AdminTechAuthContext, tenant_id: UUID
) -> platform_repository.TenantRecord | None:
    """Resuelve un tenant desde la sesión de plataforma, sin confiar en el slug del cliente."""
    for tenant in await platform_repository.list_tenants(identity.session):
        if tenant.id == tenant_id:
            return tenant
    return None


async def list_pending(
    identity: AdminTechAuthContext, *, cursor: str | None, limit: int
) -> GlobalPendingPage:
    cursor_created_at: datetime | None = None
    cursor_id: UUID | None = None
    if cursor is not None:
        cursor_created_at, cursor_id = _decode_cursor(cursor)

    tenants = await platform_repository.list_tenants(identity.session)
    result: list[GlobalPending] = []
    for tenant in tenants:
        async with tenant_session(tenant.id) as session:
            page = await invoicing_repository.list_supervision(
                session,
                actor_user_id=identity.user_id,
                limit=limit + 1,
                cursor_created_at=cursor_created_at,
                cursor_id=cursor_id,
                encryption_key=tenant_encryption_key(get_settings(), tenant.id),
            )
            result.extend(
                GlobalPending(
                    tenant_id=tenant.id,
                    tenant_slug=tenant.slug,
                    id=item.id,
                    user_email=item.user_email,
                    company_name=item.company_name,
                    status=item.status,
                    created_at=item.created_at,
                    direction=item.direction,
                    page_count=item.page_count,
                )
                for item in page.items
            )
    result = sorted(result, key=lambda item: (item.created_at, item.id), reverse=True)
    page_items = result[:limit]
    return GlobalPendingPage(
        items=page_items,
        next_cursor=(
            _encode_cursor(page_items[-1].created_at, page_items[-1].id)
            if len(result) > limit and page_items
            else None
        ),
    )


async def open_readonly(
    identity: AdminTechAuthContext,
    *,
    tenant_id: UUID,
    tenant_slug: str,
    file_id: UUID,
    request_id: str | None,
    source_ip: str | None,
) -> invoicing_service.ReviewData:
    async with tenant_session(tenant_id) as session:
        context = AuthContext(
            user_id=identity.user_id,
            tenant_id=tenant_id,
            role="tenant_admin",
            tenant_slug=tenant_slug,
            session=session,
            company=None,
        )
        file_context = await intake_repository.get_file_context(session, file_id)
        if file_context is None:
            raise invoicing_service.FileNotVisible
        data = await invoicing_service.review(context, file_id, readonly=True)
        await write_audit(
            session,
            actor_id=identity.user_id,
            action="admin_tech.pending_document.read",
            entity="uploaded_file",
            entity_id=file_id,
            payload={
                "tenant_id": str(tenant_id),
                "company_id": str(file_context.company_id),
                "uploaded_file_id": str(file_id),
            },
            request_id=request_id,
            source_ip=source_ip,
        )
        return data

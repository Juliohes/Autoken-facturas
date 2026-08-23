"""Retención diaria de documentos no confirmados (R-028)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from invoice_intake import repository as intake_repository
from invoice_intake import storage
from platform_admin import repository as platform_repository
from shared.audit import write_audit
from shared.config import get_settings
from shared.db import platform_session, tenant_session

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class RetentionOutcome:
    expired_pending_count: int
    purge_storage_failures: int


async def _increment_metrics(
    *, expired_count: int, storage_failures: int
) -> None:
    if expired_count == 0 and storage_failures == 0:
        return
    async with platform_session() as session:
        await session.execute(
            text(
                "INSERT INTO retention_metrics "
                "(id, expired_pending_count, purge_storage_failures, updated_at) "
                "VALUES (true, :expired_count, :storage_failures, now()) "
                "ON CONFLICT (id) DO UPDATE SET "
                "expired_pending_count = retention_metrics.expired_pending_count "
                "+ EXCLUDED.expired_pending_count, "
                "purge_storage_failures = retention_metrics.purge_storage_failures "
                "+ EXCLUDED.purge_storage_failures, "
                "updated_at = now()"
            ),
            {"expired_count": expired_count, "storage_failures": storage_failures},
        )


async def _remove_locations(locations: list[tuple[str, str]]) -> int:
    failures = 0
    for bucket, key in locations:
        try:
            await asyncio.to_thread(storage.remove_object, bucket, key)
        except storage.StorageUnavailable:
            failures += 1
            logger.warning("retention.storage_removal_failed", extra={"bucket": bucket, "key": key})
    return failures


async def purge_expired_unconfirmed_documents() -> RetentionOutcome:
    """Purga DB-first y elimina después los objetos de MinIO de forma best-effort."""
    settings = get_settings()
    expired_count = 0
    storage_failures = 0
    for tenant in await _list_tenants():
        locations: list[tuple[str, str]] = []
        async with tenant_session(tenant.id) as session:
            candidates = await intake_repository.list_expired_unconfirmed_files(
                session, limit=settings.retention_batch_size
            )
            for candidate in candidates:
                pages = await intake_repository.get_document_pages(session, candidate.id)
                await intake_repository.delete_review_draft(session, candidate.id)
                await intake_repository.delete_uploaded_file(session, candidate.id)
                await write_audit(
                    session,
                    actor_id=None,
                    action="retention.pending_document.purge",
                    entity="uploaded_file",
                    entity_id=candidate.id,
                    payload={"uploaded_file_id": str(candidate.id)},
                )
                locations.extend((page.bucket, page.key) for page in pages)
                expired_count += 1
        storage_failures += await _remove_locations(locations)

    await _increment_metrics(
        expired_count=expired_count, storage_failures=storage_failures
    )
    return RetentionOutcome(
        expired_pending_count=expired_count,
        purge_storage_failures=storage_failures,
    )


async def _list_tenants() -> list[platform_repository.TenantRecord]:
    async with platform_session() as session:
        return await platform_repository.list_tenants(session)


async def read_retention_metrics() -> RetentionOutcome | None:
    async with platform_session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT expired_pending_count, purge_storage_failures "
                    "FROM retention_metrics WHERE id = true"
                )
            )
        ).first()
    if row is None:
        return None
    return RetentionOutcome(
        expired_pending_count=row.expired_pending_count,
        purge_storage_failures=row.purge_storage_failures,
    )


async def purge_expired_unconfirmed_documents_task(_ctx: dict[str, Any]) -> None:
    await purge_expired_unconfirmed_documents()

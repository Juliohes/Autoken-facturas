"""Pruebas de comportamiento R-028: retención de documentos no confirmados."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import asyncpg

from invoice_intake import storage
from jobs.retention import purge_expired_unconfirmed_documents
from tests._invoicing import seed_confirmable


async def _set_old(dsns: dict[str, str], file_id: str, *, status: str | None = None) -> None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "UPDATE uploaded_files SET created_at = $1, status = COALESCE($2, status) "
            "WHERE id = $3",
            datetime.now(UTC) - timedelta(days=365),
            status,
            file_id,
        )
    finally:
        await conn.close()


async def test_r028_purga_solo_antiguos_no_confirmados_y_audita(authapi) -> None:
    _client, dsns = authapi
    old = await seed_confirmable(dsns, _client, slug="retention-old")
    fresh = await seed_confirmable(dsns, _client, slug="retention-fresh")
    confirmed = await seed_confirmable(dsns, _client, slug="retention-confirmed")
    await _set_old(dsns, old["file_id"])
    await _set_old(dsns, confirmed["file_id"], status="confirmed")

    result = await purge_expired_unconfirmed_documents()

    assert result.expired_pending_count == 1
    conn = await asyncpg.connect(dsns["admin"])
    try:
        remaining = await conn.fetchval(
            "SELECT count(*) FROM uploaded_files WHERE id = ANY($1::uuid[])",
            [old["file_id"], fresh["file_id"], confirmed["file_id"]],
        )
        audit = await conn.fetchrow(
            "SELECT actor_id, action, payload_hash FROM audit_log "
            "WHERE entity_id = $1 AND action = 'retention.pending_document.purge'",
            old["file_id"],
        )
    finally:
        await conn.close()

    assert remaining == 2
    assert audit is not None
    assert audit["actor_id"] is None
    assert audit["payload_hash"]


async def test_r028_fallo_de_storage_no_revierte_borrado_db(authapi, monkeypatch) -> None:
    _client, dsns = authapi
    old = await seed_confirmable(dsns, _client, slug="retention-storage-failure")
    await _set_old(dsns, old["file_id"])

    def fail_remove(_bucket: str, _key: str) -> None:
        raise storage.StorageUnavailable("fallo de prueba")

    monkeypatch.setattr(storage, "remove_object", fail_remove)
    result = await purge_expired_unconfirmed_documents()

    assert result.expired_pending_count == 1
    assert result.purge_storage_failures == 1
    conn = await asyncpg.connect(dsns["admin"])
    try:
        file_count = await conn.fetchval(
            "SELECT count(*) FROM uploaded_files WHERE id = $1", old["file_id"]
        )
        metrics = await conn.fetchrow(
            "SELECT expired_pending_count, purge_storage_failures "
            "FROM retention_metrics WHERE id = true"
        )
    finally:
        await conn.close()

    assert file_count == 0
    assert metrics["expired_pending_count"] == 1
    assert metrics["purge_storage_failures"] == 1

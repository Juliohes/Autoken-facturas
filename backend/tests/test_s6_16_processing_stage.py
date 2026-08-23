"""Pruebas de comportamiento de progreso durable y cercado del OCR (R-016/R-017)."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from invoice_intake import repository
from invoice_intake.constants import FileStatus, ProcessingStage
from shared.db import tenant_session
from tests._auth import USER_PASSWORD_HASH
from tests._dbtest import seed_company, seed_membership, seed_tenant, seed_user
from tests._intake import auth as intake_auth
from tests._intake import token_for
from tests._ocr import build_extracted, make_extractor, run_ocr, seed_uploaded_file

Api = tuple[object, dict[str, str]]


async def _seed(dsns: dict[str, str], slug: str) -> tuple[str, str, str]:
    tenant_id = await seed_tenant(dsns["admin"], slug, f"{slug.upper()} Asesoría")
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email=f"ana@{slug}.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif="A39031620"
    )
    await seed_membership(
        dsns["admin"], user_id=user_id, company_id=company_id, tenant_id=tenant_id
    )
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )
    return tenant_id, company_id, file_id


async def _stage_row(dsns: dict[str, str], file_id: str) -> asyncpg.Record:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return await conn.fetchrow(
            "SELECT status, processing_stage, ocr_started_at, ocr_finished_at "
            "FROM uploaded_files WHERE id = $1",
            file_id,
        )
    finally:
        await conn.close()


async def test_ocr_persiste_etapas_y_timestamps_y_limpia_la_etapa_final(
    authapi: Api, monkeypatch
) -> None:
    """El worker expone etapas reales y no deja progreso falso al terminar."""
    import jobs.ocr as ocr_job

    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, "processing-stage")
    observed: list[ProcessingStage] = []
    original_update = ocr_job.intake_repo.update_processing_stage

    async def observe_update(session, uploaded_file_id, *, claim_token, stage):
        observed.append(stage)
        return await original_update(
            session, uploaded_file_id, claim_token=claim_token, stage=stage
        )

    monkeypatch.setattr(ocr_job.intake_repo, "update_processing_stage", observe_update)

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(build_extracted()),
    )

    row = await _stage_row(dsns, file_id)
    assert observed == [
        ProcessingStage.PRIMARY_OCR,
        ProcessingStage.VALIDATING,
        ProcessingStage.PERSISTING,
    ]
    assert row["status"] == FileStatus.OCR_DONE.value
    assert row["processing_stage"] is None
    assert row["ocr_started_at"] is not None
    assert row["ocr_finished_at"] is not None
    assert row["ocr_finished_at"] >= row["ocr_started_at"]


async def test_un_worker_antiguo_no_puede_actualizar_processing_stage(authapi: Api) -> None:
    """El token de fencing impide que un claim vencido cambie el progreso del claim nuevo."""
    _client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, "processing-fencing")
    tenant_uuid, company_uuid, file_uuid = UUID(tenant_id), UUID(company_id), UUID(file_id)

    async with tenant_session(tenant_uuid, company_uuid) as session:
        old_token = await repository.claim_ocr(session, file_uuid, company_uuid, lease_seconds=60)
    assert old_token is not None

    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "UPDATE uploaded_files SET ocr_claim_expires_at = now() - interval '1 second' "
            "WHERE id = $1",
            file_id,
        )
    finally:
        await conn.close()

    async with tenant_session(tenant_uuid, company_uuid) as session:
        new_token = await repository.claim_ocr(session, file_uuid, company_uuid, lease_seconds=60)
        assert new_token is not None and new_token != old_token
        assert (
            await repository.update_processing_stage(
                session, file_uuid, claim_token=old_token, stage=ProcessingStage.PRIMARY_OCR
            )
            is False
        )

    row = await _stage_row(dsns, file_id)
    assert row["status"] == FileStatus.PROCESSING.value
    assert row["processing_stage"] == ProcessingStage.LOADING_DOCUMENT.value


async def test_status_endpoint_devuelve_solo_progreso_y_respeta_la_privacidad(authapi: Api) -> None:
    """El status es pequeño, no contiene PII y un usuario puede ver solo su propio fichero."""
    client, dsns = authapi
    tenant_id, company_id, file_id = await _seed(dsns, "processing-status")
    token = await token_for(
        client, email="ana@processing-status.es", hostname="processing-status.localhost"
    )

    response = await client.get(
        f"/api/v1/uploads/{file_id}/status",
        headers=intake_auth(token, hostname="processing-status.localhost"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == file_id
    assert body["status"] == FileStatus.PENDING_OCR.value
    assert body["processing_stage"] == ProcessingStage.QUEUED.value
    assert body["ocr_started_at"] is None
    assert body["ocr_finished_at"] is None
    assert (
        not {
            "sha256",
            "storage_key",
            "storage_bucket",
            "raw",
            "counterparty_tax_id",
        }
        & body.keys()
    )

    other_user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="otro@processing-status.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(
        dsns["admin"], user_id=other_user_id, company_id=company_id, tenant_id=tenant_id
    )
    other_token = await token_for(
        client, email="otro@processing-status.es", hostname="processing-status.localhost"
    )
    private_response = await client.get(
        f"/api/v1/uploads/{file_id}/status",
        headers=intake_auth(other_token, hostname="processing-status.localhost"),
    )
    assert private_response.status_code == 404

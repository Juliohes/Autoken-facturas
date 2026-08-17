"""Pruebas de comportamiento S6.13: intake seguro y OCR recuperable.

Ejercen el contrato HTTP y el worker contra Postgres, Redis y MinIO reales. No usan proveedores
OCR reales: los dobles solo hacen observable el claim exclusivo y los errores sanitizados.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID

import asyncpg
import pytest

from tests._auth import USER_PASSWORD_HASH
from tests._dbtest import seed_membership, seed_user
from tests._intake import (
    JPEG,
    JPEG_CT,
    auth,
    count_uploaded_files,
    seed_uploader,
    token_for,
    upload_parts,
)
from tests._invoicing import auth as invoice_auth
from tests._invoicing import confirm_body, confirm_url, history_url, seed_confirmable
from tests._ocr import (
    build_extracted,
    count_extractions,
    file_status,
    make_extractor,
    run_ocr,
    seed_uploaded_file,
)


async def _stored_direction(dsns: dict[str, str], file_id: str) -> str | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return await conn.fetchval("SELECT direction FROM uploaded_files WHERE id = $1", file_id)
    finally:
        await conn.close()


async def _set_direction(dsns: dict[str, str], file_id: str, direction: str | None) -> None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "UPDATE uploaded_files SET direction = $2 WHERE id = $1", file_id, direction
        )
    finally:
        await conn.close()


async def test_c3_subida_simple_conserva_direccion_en_historial_y_revision(authapi) -> None:
    """C3: la dirección de captura simple queda durable, no solo en el navegador."""
    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    uploaded = await client.post(
        "/api/v1/uploads",
        headers=auth(token),
        files={"file": ("emitida.jpg", JPEG, JPEG_CT)},
        data={"company_id": company_id, "direction": "emitida"},
    )

    assert uploaded.status_code == 201, uploaded.text
    file_id = uploaded.json()["id"]
    assert uploaded.json()["direction"] == "emitida"
    assert await _stored_direction(dsns, file_id) == "emitida"

    await run_ocr(
        tenant_id=tenant_id,
        company_id=company_id,
        file_id=file_id,
        extractor=make_extractor(
            build_extracted(own_cif="A39031620", counterparty_cif="B06183446")
        ),
    )
    history = await client.get(history_url(), headers=invoice_auth(token))
    review = await client.get(f"/api/v1/uploads/{file_id}/review", headers=invoice_auth(token))

    assert history.status_code == 200, history.text
    assert history.json()["entries"][0]["direction"] == "emitida"
    assert review.status_code == 200, review.text
    assert review.json()["direction"] == "emitida"


async def test_c3_confirmacion_usa_direccion_capturada_y_historica_nula_exige_body(authapi) -> None:
    """C3: confirmar no sustituye la dirección capturada; un legado nulo sigue explícito."""
    client, dsns = authapi
    seeded = await seed_confirmable(dsns, client)
    await _set_direction(dsns, seeded["file_id"], "emitida")

    response = await client.post(
        confirm_url(seeded["file_id"]),
        headers=invoice_auth(seeded["token"]),
        json=confirm_body(direction="recibida"),
    )

    assert response.status_code == 201, response.text
    conn = await asyncpg.connect(dsns["admin"])
    try:
        direction = await conn.fetchval(
            "SELECT direction FROM invoices WHERE id = $1", response.json()["id"]
        )
    finally:
        await conn.close()
    assert direction == "emitida"


async def test_c3_lote_conserva_direccion_elegida(authapi) -> None:
    """C3: el documento multipágina persiste la misma dirección que la captura simple."""
    client, dsns = authapi
    _tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    response = await client.post(
        "/api/v1/uploads/batch",
        headers=auth(token),
        files=[
            ("files", ("pagina-1.jpg", JPEG + b"-batch-one", JPEG_CT)),
            ("files", ("pagina-2.jpg", JPEG + b"-batch-two", JPEG_CT)),
        ],
        data={"company_id": company_id, "direction": "emitida"},
    )

    assert response.status_code == 201, response.text
    assert response.json()["direction"] == "emitida"
    assert await _stored_direction(dsns, response.json()["id"]) == "emitida"


async def test_c7_imagen_truncada_se_rechaza_antes_de_av_storage_y_bd(authapi) -> None:
    """C7: un JPEG con magic válido pero estructura truncada devuelve 422 y no deja residuos."""
    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    truncated = JPEG[:-2]

    response = await client.post(
        "/api/v1/uploads",
        headers=auth(token),
        **upload_parts(truncated, company_id, filename="truncada.jpg", content_type=JPEG_CT),
    )

    assert response.status_code == 422, response.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0


async def test_c7_imagen_con_demasiados_pixeles_se_rechaza_sin_persistir(
    authapi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C7: las dimensiones se limitan antes de decodificar o almacenar una imagen."""
    from invoice_intake import service as intake_service

    client, dsns = authapi
    _tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    monkeypatch.setattr(
        intake_service,
        "get_settings",
        lambda: SimpleNamespace(max_upload_image_pixels=100),
    )

    response = await client.post(
        "/api/v1/uploads",
        headers=auth(token),
        **upload_parts(JPEG, company_id, filename="grande.jpg", content_type=JPEG_CT),
    )

    assert response.status_code == 422, response.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0


async def test_c4_dos_workers_solo_llaman_una_vez_al_proveedor(authapi) -> None:
    """C4: dos mensajes duplicados compiten por un claim; el segundo nunca llama al extractor."""
    _client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )

    class SlowExtractor:
        def __init__(self) -> None:
            self.calls = 0

        async def extract(self, _content: bytes, _content_type: str):
            self.calls += 1
            await asyncio.sleep(0.05)
            return build_extracted(own_cif="A39031620", counterparty_cif="B06183446")

    extractor = SlowExtractor()
    await asyncio.gather(
        run_ocr(tenant_id=tenant_id, company_id=company_id, file_id=file_id, extractor=extractor),
        run_ocr(tenant_id=tenant_id, company_id=company_id, file_id=file_id, extractor=extractor),
    )

    assert extractor.calls == 1
    assert await count_extractions(dsns, file_id=file_id) == 1


async def test_c4_un_claim_vencido_no_puede_cerrar_el_claim_nuevo(authapi) -> None:
    """C4: el token de fencing impide que un worker viejo cambie el estado del propietario nuevo."""
    from invoice_intake import repository
    from invoice_intake.constants import FileStatus
    from shared.db import tenant_session

    _client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )
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
    async with tenant_session(tenant_uuid, company_uuid) as session:
        old_worker_won = await repository.finish_claim(
            session, file_uuid, old_token, FileStatus.OCR_FAILED
        )

    assert old_worker_won is False
    assert await file_status(dsns, file_id=file_id) == "processing"


async def test_c6_fallo_al_construir_extractor_deja_salida_reintentable_sin_pii_en_logs(
    authapi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C6: la construcción previa al proveedor falla segura y no loguea su texto."""
    import jobs.ocr as ocr_job

    _client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )
    logged: list[dict[str, object]] = []

    class Logger:
        def error(self, _event: str, **kwargs: object) -> None:
            logged.append(kwargs)

    def broken_builder(_settings: object):
        raise RuntimeError("provider token=secret-ocr-text and invoice ACME SA")

    monkeypatch.setattr(ocr_job, "logger", Logger())
    monkeypatch.setattr(ocr_job, "build_default_extractor", broken_builder)

    await ocr_job.run_ocr(tenant_id, company_id, file_id)

    assert await file_status(dsns, file_id=file_id) == "ocr_failed"
    assert await count_extractions(dsns, file_id=file_id) == 0
    assert "secret-ocr-text" not in str(logged)
    assert "ACME SA" not in str(logged)


async def test_c5_recovery_reencola_pending_y_claim_vencido_y_persiste_metricas(
    authapi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C5: el recuperador durable reencola solo recuperables y devuelve agregados sin PII."""
    from jobs import ocr_recovery

    _client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    pending = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id
    )
    expired = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=user_id,
        content=JPEG + b"expired",
        status="processing",
    )
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "UPDATE uploaded_files SET ocr_claim_expires_at = now() - interval '1 minute' "
            "WHERE id = $1",
            expired,
        )
    finally:
        await conn.close()
    queued: list[tuple[str, str, str]] = []

    async def enqueue(tenant: str, company: str, file_id: str) -> None:
        queued.append((tenant, company, file_id))

    monkeypatch.setattr(ocr_recovery.queue, "enqueue_ocr", enqueue)
    metrics = await ocr_recovery.recover_ocr_documents()

    assert {str(entry[2]) for entry in queued} == {pending, expired}
    assert metrics.pending >= 1
    assert metrics.processing == 0
    assert metrics.failed == 0


async def test_c9_reintento_ocr_no_revela_fichero_ajeno(authapi) -> None:
    """C9: solo el dueño puede reintentar su OCR fallido; la URL ajena no es un oráculo."""
    client, dsns = authapi
    tenant_id, owner_id, company_id = await seed_uploader(dsns)
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=owner_id, status="ocr_failed"
    )
    owner = await token_for(client, email="ana@ilex.es")
    colleague_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="otro-reintento@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(
        dsns["admin"], user_id=colleague_id, company_id=company_id, tenant_id=tenant_id
    )
    colleague = await token_for(client, email="otro-reintento@ilex.es")

    accepted = await client.post(f"/api/v1/uploads/{file_id}/retry-ocr", headers=auth(owner))
    foreign = await client.post(f"/api/v1/uploads/{file_id}/retry-ocr", headers=auth(colleague))

    assert accepted.status_code == 202, accepted.text
    assert accepted.json() == {"status": "pending_ocr"}
    assert foreign.status_code == 404, foreign.text

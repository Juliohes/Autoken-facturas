"""Pruebas de comportamiento S6.12 para documentos multipagina e historial privado.

Los casos ejercen la API ASGI contra Postgres, Redis, MinIO y ClamAV reales. El contrato HTTP del
lote fija un unico endpoint: ``POST /api/v1/uploads/batch`` con una parte multipart ``files`` por
pagina, ``company_id`` y ``direction``. Un lote aceptado representa un solo documento.
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

import asyncpg
import httpx
import pytest

from tests._auth import USER_PASSWORD_HASH
from tests._dbtest import seed_company, seed_membership, seed_user
from tests._intake import (
    JPEG,
    JPEG_CT,
    NOT_AN_IMAGE,
    auth,
    count_uploaded_file_pages,
    count_uploaded_files,
    object_exists,
    seed_tenant_admin,
    seed_uploader,
    token_for,
)
from tests._invoicing import fetch_invoice_by_id, history_url, seed_invoice
from tests._ocr import seed_uploaded_file

Api = tuple[httpx.AsyncClient, dict[str, str]]

BATCH_UPLOADS = "/api/v1/uploads/batch"


def batch_upload_parts(
    pages: list[tuple[str, bytes]], company_id: str, *, direction: str = "recibida"
) -> dict[str, object]:
    """Cuerpo multipart de un documento: conserva el orden de las partes ``files``."""
    return {
        "files": [("files", (filename, content, JPEG_CT)) for filename, content in pages],
        "data": {"company_id": company_id, "direction": direction},
    }


async def set_uploaded_at(dsns: dict[str, str], file_id: str, when: datetime) -> None:
    """Fija el instante de envio para probar el corte y orden del historial."""
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute("UPDATE uploaded_files SET created_at = $2 WHERE id = $1", file_id, when)
    finally:
        await conn.close()


async def test_c8_lote_multipagina_crea_un_documento_y_encola_un_solo_ocr(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C8: tres paginas ordenadas -> 201, un documento persistido y un unico OCR encolado."""
    # spec: C8
    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    enqueued: list[tuple[object, ...]] = []

    from invoice_intake import service

    async def record_ocr(*args: object) -> bool:
        enqueued.append(args)
        return True

    monkeypatch.setattr(service.queue, "enqueue_ocr", record_ocr)
    pages = [
        ("01-fiscal.jpg", JPEG + b"-fiscal"),
        ("02-importes.jpg", JPEG + b"-importes"),
        ("03-complementaria.jpg", JPEG + b"-complementaria"),
    ]

    response = await client.post(
        BATCH_UPLOADS,
        headers=auth(token),
        **batch_upload_parts(pages, company_id, direction="emitida"),
    )

    assert response.status_code == 201, response.text
    document_id = response.json()["id"]
    assert await count_uploaded_files(dsns, company_id=company_id) == 1
    assert await count_uploaded_file_pages(dsns, root_uploaded_file_id=document_id) == 2
    await asyncio.sleep(0)  # el dispatcher se crea desde el callback síncrono post-commit
    assert len(enqueued) == 1
    assert str(enqueued[0][-1]) == document_id
    # El documento, no cada pagina, es la unica unidad que el OCR recibe del intake.
    assert str(enqueued[0][0]) == tenant_id


async def test_lote_y_subida_simple_del_mismo_hash_no_comparten_objeto_ni_dejan_huerfanos(
    authapi: Api,
) -> None:
    """La garantía SQL global serializa batch-vs-single sin borrar la clave del ganador."""
    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    shared = JPEG + b"-hash-race"

    async def upload_single() -> httpx.Response:
        return await client.post(
            "/api/v1/uploads",
            headers=auth(token),
            files={"file": ("single.jpg", shared, JPEG_CT)},
            data={"company_id": company_id},
        )

    async def upload_batch() -> httpx.Response:
        return await client.post(
            BATCH_UPLOADS,
            headers=auth(token),
            **batch_upload_parts(
                [("first.jpg", shared), ("second.jpg", JPEG + b"-second-race")], company_id
            ),
        )

    single, batch = await asyncio.gather(upload_single(), upload_batch())

    assert sorted([single.status_code, batch.status_code]) == [201, 409], (single.text, batch.text)
    assert await count_uploaded_files(dsns, company_id=company_id) == 1
    assert await object_exists(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        sha256=hashlib.sha256(shared).hexdigest(),
    )


async def test_dos_usuarios_de_la_misma_empresa_pueden_subir_el_mismo_documento(
    authapi: Api,
) -> None:
    """La deduplicación es privada: cada usuario conserva su propio documento y su propio 409."""
    client, dsns = authapi
    tenant_id, alice_id, company_id = await seed_uploader(dsns)
    alice_token = await token_for(client, email="ana@ilex.es")
    bob_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="bob-dedup-privado@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(dsns["admin"], user_id=bob_id, company_id=company_id, tenant_id=tenant_id)
    bob_token = await token_for(client, email="bob-dedup-privado@ilex.es")
    pages = [("01.jpg", JPEG + b"-dedup-private-one"), ("02.jpg", JPEG + b"-dedup-private-two")]

    alice = await client.post(
        BATCH_UPLOADS, headers=auth(alice_token), **batch_upload_parts(pages, company_id)
    )
    bob = await client.post(
        BATCH_UPLOADS, headers=auth(bob_token), **batch_upload_parts(pages, company_id)
    )
    bob_duplicate = await client.post(
        BATCH_UPLOADS, headers=auth(bob_token), **batch_upload_parts(pages, company_id)
    )

    assert alice.status_code == 201, alice.text
    assert bob.status_code == 201, bob.text
    assert bob_duplicate.status_code == 409, bob_duplicate.text
    assert bob_duplicate.json()["duplicate_of"] == bob.json()["id"]
    assert bob_duplicate.json()["duplicate_of"] != alice.json()["id"]
    assert await count_uploaded_files(dsns, company_id=company_id) == 2


async def test_c10_pagina_invalida_rechaza_el_lote_sin_dejar_paginas_parciales(
    authapi: Api,
) -> None:
    """C10: una segunda pagina no imagen -> 415, sin filas ni objeto de la primera pagina."""
    # spec: C10
    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    valid_page = JPEG + b"-primera-valida"

    response = await client.post(
        BATCH_UPLOADS,
        headers=auth(token),
        **batch_upload_parts(
            [("01-fiscal.jpg", valid_page), ("02-importes.jpg", NOT_AN_IMAGE)], company_id
        ),
    )

    assert response.status_code == 415, response.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0
    assert not await object_exists(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        sha256=hashlib.sha256(valid_page).hexdigest(),
    )


async def test_lote_compensa_la_pagina_cuyo_guardado_pudo_completar_antes_de_fallar(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un error ambiguo de MinIO tras escribir una página no deja objetos huérfanos."""
    client, dsns = authapi
    _tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    from invoice_intake import storage

    original_put_object = storage.put_object
    attempted_locations: list[tuple[str, str]] = []

    def put_then_report_failure(
        bucket: str, key: str, data: bytes, length: int, content_type: str
    ) -> None:
        original_put_object(bucket, key, data, length, content_type)
        attempted_locations.append((bucket, key))
        if len(attempted_locations) == 2:
            raise storage.StorageUnavailable("la respuesta de MinIO se perdió tras escribir")

    monkeypatch.setattr(storage, "put_object", put_then_report_failure)
    response = await client.post(
        BATCH_UPLOADS,
        headers=auth(token),
        **batch_upload_parts(
            [("01.jpg", JPEG + b"-ambiguous-first"), ("02.jpg", JPEG + b"-ambiguous-second")],
            company_id,
        ),
    )

    try:
        assert response.status_code == 503, response.text
        assert len(attempted_locations) == 2
        assert await count_uploaded_files(dsns, company_id=company_id) == 0
        assert all(not storage.object_exists(bucket, key) for bucket, key in attempted_locations)
    finally:
        # Si falla contra una versión vulnerable, no se deja el huérfano en MinIO de test.
        for bucket, key in attempted_locations:
            storage.remove_object(bucket, key)


async def test_documento_multipagina_exige_entre_dos_y_cinco_paginas(authapi: Api) -> None:
    """Invariante S6.12: uno o seis ficheros no forman un documento y no dejan rastro."""
    # spec: C7
    client, dsns = authapi
    _tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    one_page = await client.post(
        BATCH_UPLOADS,
        headers=auth(token),
        **batch_upload_parts([("01.jpg", JPEG + b"-one")], company_id),
    )
    six_pages = await client.post(
        BATCH_UPLOADS,
        headers=auth(token),
        **batch_upload_parts(
            [(f"{number}.jpg", JPEG + f"-{number}".encode()) for number in range(1, 7)],
            company_id,
        ),
    )

    assert one_page.status_code == 422, one_page.text
    assert six_pages.status_code == 422, six_pages.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0


async def test_c11_historial_privado_corta_a_veinte_e_incluye_pendientes_y_fallidos(
    authapi: Api,
) -> None:
    """C11: 21 envios propios + una factura de prueba -> solo los 20 documentos no de prueba."""
    # spec: C11
    client, dsns = authapi
    tenant_id, user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    sent_at = datetime.now(UTC)
    expected_ids: list[str] = []
    expected_statuses: dict[str, str] = {}

    for index in range(21):
        status = "pending_ocr" if index == 0 else "ocr_failed" if index == 1 else "needs_review"
        file_id = await seed_uploaded_file(
            dsns,
            tenant_id=tenant_id,
            company_id=company_id,
            uploaded_by=user_id,
            content=JPEG + f"-history-{index}".encode(),
            status=status,
        )
        await set_uploaded_at(dsns, file_id, sent_at - timedelta(minutes=index))
        expected_ids.append(file_id)
        expected_statuses[file_id] = status

    test_invoice_id = await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        is_test=True,
        confirmed_by=user_id,
    )
    test_invoice = await fetch_invoice_by_id(dsns, invoice_id=test_invoice_id)
    assert test_invoice is not None

    response = await client.get(history_url(), headers=auth(token))

    assert response.status_code == 200, response.text
    entries = response.json()["entries"]
    assert [entry["id"] for entry in entries] == expected_ids[:20]
    assert [entry["status"] for entry in entries] == [
        expected_statuses[file_id] for file_id in expected_ids[:20]
    ]
    assert str(test_invoice["uploaded_file_id"]) not in {entry["id"] for entry in entries}
    assert all("counterparty_tax_id" not in entry for entry in entries)


async def test_c11_y_c13_un_user_no_lista_ni_descarga_el_documento_de_su_companero(
    authapi: Api,
) -> None:
    """C11/C13: misma empresa no da visibilidad al historial ni a los bytes de otro ``user``."""
    # spec: C11, C13
    client, dsns = authapi
    tenant_id, alice_id, company_id = await seed_uploader(dsns)
    alice_token = await token_for(client, email="ana@ilex.es")
    bob_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="bob-multipagina@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(dsns["admin"], user_id=bob_id, company_id=company_id, tenant_id=tenant_id)
    own_file = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=alice_id,
        content=JPEG + b"-alice-history",
    )
    colleague_file = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=bob_id,
        content=JPEG + b"-bob-private-page",
    )

    history = await client.get(history_url(), headers=auth(alice_token))
    image = await client.get(f"/api/v1/uploads/{colleague_file}/image", headers=auth(alice_token))

    assert history.status_code == 200, history.text
    assert {entry["id"] for entry in history.json()["entries"]} == {own_file}
    # No se distingue un documento existente de uno inexistente por una URL directa.
    assert image.status_code == 404, image.text


async def test_c12_tenant_admin_ve_documentos_de_toda_su_asesoria_sin_cruzar_tenant(
    authapi: Api,
) -> None:
    """C12: el administrador conserva la vista de dos empresas, no la de otro tenant."""
    # spec: C12
    client, dsns = authapi
    tenant_id, _admin_id = await seed_tenant_admin(dsns)
    company_a = await seed_company(dsns["admin"], tenant_id=tenant_id, name="A", cif="A39031620")
    company_b = await seed_company(dsns["admin"], tenant_id=tenant_id, name="B", cif="B06183446")
    uploader_a = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="a-admin-history@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    uploader_b = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="b-admin-history@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    own_a = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_a,
        uploaded_by=uploader_a,
        content=JPEG + b"-a",
    )
    own_b = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_b,
        uploaded_by=uploader_b,
        content=JPEG + b"-b",
    )
    other_tenant, other_uploader, other_company = await seed_uploader(
        dsns, slug="other-history", email="other-history@example.com"
    )
    foreign_file = await seed_uploaded_file(
        dsns,
        tenant_id=other_tenant,
        company_id=other_company,
        uploaded_by=other_uploader,
        content=JPEG + b"-other-tenant",
    )
    admin_token = await token_for(client, email="admin@ilex.es")

    response = await client.get(history_url(), headers=auth(admin_token))

    assert response.status_code == 200, response.text
    ids = {entry["id"] for entry in response.json()["entries"]}
    assert ids == {own_a, own_b}
    assert foreign_file not in ids

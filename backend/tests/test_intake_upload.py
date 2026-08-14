"""Tests de comportamiento S2.1: Upload seguro de ficheros de factura (spec docs/specs/S2.1).

Criterios C1-C14. Observable vía HTTP (cliente ASGI con `Host` de tenant) contra Postgres real +
Redis + MinIO real, con antivirus real (detecta la firma EICAR) e inyección de fallos para el AV
caído (C7) y el almacén caído (C12). Fase roja: el endpoint `POST /api/v1/uploads` aún no existe.
"""

from __future__ import annotations

import asyncio
import hashlib

import httpx
import pytest

from tests._dbtest import seed_company
from tests._intake import (
    EICAR_JPEG,
    JPEG,
    JPEG_CT,
    NOT_AN_IMAGE,
    PDF,
    PDF_CT,
    PNG,
    PNG_CT,
    UPLOADS,
    audit_entries,
    auth,
    count_uploaded_files,
    object_exists,
    seed_tenant_admin,
    seed_uploader,
    token_for,
    upload_parts,
)

Api = tuple[httpx.AsyncClient, dict[str, str]]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- Subida válida -------------------------------------------------------------------------------
async def test_c1_subir_imagen_valida(authapi: Api) -> None:
    """C1: un empleado sube un JPEG válido a su empresa -> 201, registro y objeto persistidos."""
    client, dsns = authapi
    tenant_id, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(JPEG, company_id, filename="factura.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["company_id"] == company_id
    assert body["content_type"] == JPEG_CT
    assert body["sha256"] == _sha256(JPEG)
    assert body["size_bytes"] == len(JPEG)
    assert body["status"] == "pending_ocr"
    assert body["scan_status"] == "clean"
    assert await count_uploaded_files(dsns, company_id=company_id) == 1
    assert await object_exists(
        dsns, tenant_id=tenant_id, company_id=company_id, sha256=_sha256(JPEG)
    )


async def test_c2_subir_pdf_valido(authapi: Api) -> None:
    """C2: un PDF válido se admite igual que una imagen -> 201, content_type application/pdf."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(PDF, company_id, filename="factura.pdf", content_type=PDF_CT),
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["content_type"] == PDF_CT
    assert await count_uploaded_files(dsns, company_id=company_id) == 1


async def test_c2b_subir_png_valido(authapi: Api) -> None:
    """C2 (variante): un PNG válido se admite -> 201, content_type image/png."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(PNG, company_id, filename="factura.png", content_type=PNG_CT),
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["content_type"] == PNG_CT


# --- Validación de tipo por MIME real ------------------------------------------------------------
async def test_c3_tipo_no_admitido_se_rechaza(authapi: Api) -> None:
    """C3: un ejecutable con nombre .jpg y Content-Type image/jpeg -> 415, nada se almacena."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(NOT_AN_IMAGE, company_id, filename="factura.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 415, resp.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0


async def test_c4_decide_por_los_bytes_no_por_la_cabecera(authapi: Api) -> None:
    """C4: un JPEG válido con Content-Type genérico se acepta; un .pdf que es un exe se rechaza."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    ok = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(
            JPEG, company_id, filename="sin_ext", content_type="application/octet-stream"
        ),
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["content_type"] == JPEG_CT

    bad = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(NOT_AN_IMAGE, company_id, filename="factura.pdf", content_type=PDF_CT),
    )
    assert bad.status_code == 415, bad.text


# --- Límites y antivirus -------------------------------------------------------------------------
async def test_c5_fichero_demasiado_grande_se_rechaza(authapi: Api) -> None:
    """C5: un fichero que supera el tamaño máximo -> 413, nada se almacena (sin caerse con 500)."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    # 15 MiB + 1 byte, con cabecera JPEG válida (el tamaño se comprueba antes que el tipo).
    oversize = JPEG + b"\x00" * (15 * 1024 * 1024 + 1 - len(JPEG))
    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(oversize, company_id, filename="grande.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 413, resp.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0


async def test_c6_fichero_infectado_se_rechaza_sin_rastro(authapi: Api) -> None:
    """C6: un JPEG (tipo correcto) con firma EICAR -> 422; ni objeto en MinIO ni fila en BD."""
    client, dsns = authapi
    tenant_id, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(EICAR_JPEG, company_id, filename="virus.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 422, resp.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0
    assert not await object_exists(
        dsns,
        tenant_id=tenant_id, company_id=company_id, sha256=_sha256(EICAR_JPEG)
    )


async def test_c7_antivirus_no_disponible_fail_closed(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C7: si ClamAV no responde -> 503 (fail-closed); ningún fichero entra sin escanear."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    from invoice_intake import scanner

    def _unavailable(_content: bytes) -> None:
        raise scanner.ScannerUnavailable("clamd caído (test)")

    monkeypatch.setattr(scanner, "scan", _unavailable)

    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(JPEG, company_id, filename="factura.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 503, resp.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0


# --- Duplicados (por empresa) --------------------------------------------------------------------
async def test_c8_duplicado_en_la_misma_empresa_se_bloquea(authapi: Api) -> None:
    """C8: el mismo fichero subido dos veces a la misma empresa -> 201 y luego 409 duplicate_of."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    parts = upload_parts(JPEG, company_id, filename="factura.jpg", content_type=JPEG_CT)

    first = await client.post(UPLOADS, headers=auth(token), **parts)
    assert first.status_code == 201, first.text
    original_id = first.json()["id"]

    dup = await client.post(UPLOADS, headers=auth(token), **parts)
    assert dup.status_code == 409, dup.text
    assert dup.json()["duplicate_of"] == original_id
    assert await count_uploaded_files(dsns, company_id=company_id, sha256=_sha256(JPEG)) == 1


async def test_c9_mismo_fichero_en_otra_empresa_u_otro_tenant_si_entra(authapi: Api) -> None:
    """C9: el mismo fichero en otra empresa o en otro tenant -> 201 (no es duplicado)."""
    client, dsns = authapi
    tid_ilex, _aid = await seed_tenant_admin(dsns)
    e1 = await seed_company(dsns["admin"], tenant_id=tid_ilex, name="E1", cif="A39031620")
    e2 = await seed_company(dsns["admin"], tenant_id=tid_ilex, name="E2", cif="B06183446")
    admin = await token_for(client, email="admin@ilex.es")

    r1 = await client.post(
        UPLOADS,
        headers=auth(admin),
        **upload_parts(JPEG, e1, filename="f.jpg", content_type=JPEG_CT),
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        UPLOADS,
        headers=auth(admin),
        **upload_parts(JPEG, e2, filename="f.jpg", content_type=JPEG_CT),
    )
    assert r2.status_code == 201, r2.text  # otra empresa: no es duplicado

    # Otro tenant: su admin sube el mismo fichero a SU bucket (distinto), tampoco es duplicado.
    tid_otra, _ = await seed_tenant_admin(dsns, slug="otra", name="Otra", email="admin@otra.es")
    e3 = await seed_company(dsns["admin"], tenant_id=tid_otra, name="E3", cif="A39031620")
    admin_otra = await token_for(client, email="admin@otra.es", hostname="otra.localhost")
    r3 = await client.post(
        UPLOADS,
        headers=auth(admin_otra, "otra.localhost"),
        **upload_parts(JPEG, e3, filename="f.jpg", content_type=JPEG_CT),
    )
    assert r3.status_code == 201, r3.text


# --- Aislamiento y autenticación -----------------------------------------------------------------
async def test_c10_no_se_puede_subir_a_una_empresa_ajena(authapi: Api) -> None:
    """C10: subir a una empresa del propio tenant sin pertenecer -> 403; de otro tenant -> 404."""
    client, dsns = authapi
    tid, _uid, _own = await seed_uploader(dsns)
    ajena = await seed_company(dsns["admin"], tenant_id=tid, name="Ajena", cif="B06183446")
    token = await token_for(client, email="ana@ilex.es")

    r = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(JPEG, ajena, filename="f.jpg", content_type=JPEG_CT),
    )
    assert r.status_code == 403, r.text

    # Empresa de otro tenant: no existe en el contexto del empleado -> 404.
    tid_otra = await _tenant_id_of_or_seed(dsns, slug="otra")
    de_otro = await seed_company(dsns["admin"], tenant_id=tid_otra, name="DeOtro", cif="A39031620")
    r2 = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(JPEG, de_otro, filename="f.jpg", content_type=JPEG_CT),
    )
    assert r2.status_code == 404, r2.text


async def _tenant_id_of_or_seed(dsns: dict[str, str], *, slug: str) -> str:
    from tests._dbtest import seed_tenant  # noqa: PLC0415

    return await seed_tenant(dsns["admin"], slug, slug.upper())


async def test_c11_sin_autenticar_no_se_sube(authapi: Api) -> None:
    """C11: sin token válido -> 401, nada se almacena."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)

    resp = await client.post(
        UPLOADS,
        headers={"Host": "ilex.localhost"},
        **upload_parts(JPEG, company_id, filename="f.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 401, resp.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0


# --- Consistencia y trazabilidad -----------------------------------------------------------------
async def test_c12a_fallo_de_almacenamiento_no_deja_registro(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C12: si falla el guardado del objeto -> 503 y NO queda fila (nada de registro sin objeto)."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    from invoice_intake import storage

    def _boom(*_a: object, **_k: object) -> None:
        raise storage.StorageUnavailable("MinIO caído (test)")

    monkeypatch.setattr(storage, "put_object", _boom)

    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(JPEG, company_id, filename="f.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 503, resp.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0


async def test_c12b_fallo_al_registrar_no_deja_objeto_huerfano(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C12: si falla la escritura del registro tras guardar el objeto -> no queda huérfano."""
    client, dsns = authapi
    tenant_id, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    from invoice_intake import repository

    async def _boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("fallo al insertar (test)")

    monkeypatch.setattr(repository, "insert_uploaded_file", _boom)

    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(JPEG, company_id, filename="f.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code >= 500, resp.text
    assert await count_uploaded_files(dsns, company_id=company_id) == 0
    assert not await object_exists(
        dsns, tenant_id=tenant_id, company_id=company_id, sha256=_sha256(JPEG)
    )


async def test_c13_subida_aceptada_deja_rastro_en_audit_log(authapi: Api) -> None:
    """C13: una subida con éxito escribe una entrada intake.upload en audit_log del tenant."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(JPEG, company_id, filename="f.jpg", content_type=JPEG_CT),
    )
    assert resp.status_code == 201, resp.text
    file_id = resp.json()["id"]

    assert await audit_entries(dsns, action="intake.upload", entity_id=file_id) == 1


async def test_c14_dos_subidas_concurrentes_del_mismo_fichero_una_gana(authapi: Api) -> None:
    """C14: dos subidas simultáneas del mismo fichero a la misma empresa -> una 201 y otra 409."""
    client, dsns = authapi
    _tid, _uid, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    async def _do() -> int:
        r = await client.post(
            UPLOADS,
            headers=auth(token),
            **upload_parts(JPEG, company_id, filename="f.jpg", content_type=JPEG_CT),
        )
        return r.status_code

    codes = sorted(await asyncio.gather(_do(), _do()))
    assert codes == [201, 409], codes
    assert await count_uploaded_files(dsns, company_id=company_id, sha256=_sha256(JPEG)) == 1

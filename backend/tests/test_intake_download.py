"""Tests de comportamiento S2.7: descarga de fichero vía URL firmada (spec docs/specs/S2.7).

Criterios C1-C6 (más C7/C8 de anti-cruce v2, en test_tenant_isolation.py). Observable vía HTTP
(cliente ASGI con `Host` de tenant) contra Postgres + MinIO reales. Fase roja: el endpoint
`GET /uploads/{file_id}/download-url` aún no existe.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from shared.config import get_settings
from tests._auth import USER_PASSWORD_HASH
from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._intake import (
    JPEG,
    JPEG_CT,
    auth,
    seed_uploader,
    token_for,
    upload_parts,
)
from tests._ocr import seed_uploaded_file

Api = tuple[httpx.AsyncClient, dict[str, str]]

UPLOADS = "/api/v1/uploads"


def download_url_path(file_id: str) -> str:
    return f"{UPLOADS}/{file_id}/download-url"


def _minio_object_url(bucket: str, key: str) -> str:
    """URL directa (sin firma) al objeto en MinIO, para probar C8 (bucket no público)."""
    return f"http://{get_settings().minio_endpoint}/{bucket}/{key}"


async def _upload_and_get_file_id(client: httpx.AsyncClient, token: str, company_id: str) -> str:
    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(JPEG, company_id, filename="f.jpg", content_type=JPEG_CT),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_c1_descargar_fichero_propio_da_url_firmada_que_funciona(authapi: Api) -> None:
    """C1: la URL firmada devuelta descarga los bytes originales del fichero."""
    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    file_id = await _upload_and_get_file_id(client, token, company_id)

    resp = await client.get(download_url_path(file_id), headers=auth(token))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["expires_in"] == 300
    async with httpx.AsyncClient() as raw:
        download = await raw.get(body["url"])
    assert download.status_code == 200
    assert download.content == JPEG


async def test_c2_la_url_firmada_expira(authapi: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """C2: una URL firmada con expiración muy corta deja de funcionar pasado ese tiempo."""
    from invoice_intake import service as intake_service  # noqa: PLC0415

    monkeypatch.setattr(intake_service, "DOWNLOAD_URL_TTL_SECONDS", 1)
    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    file_id = await _upload_and_get_file_id(client, token, company_id)

    resp = await client.get(download_url_path(file_id), headers=auth(token))
    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]

    await asyncio.sleep(2)
    async with httpx.AsyncClient() as raw:
        download = await raw.get(url)
    assert download.status_code != 200


async def test_c3_descargar_fichero_de_empresa_hermana_da_403(authapi: Api) -> None:
    """C3: fichero de otra empresa del mismo tenant -> 403; no se genera URL."""
    client, dsns = authapi
    tenant_id, _user_id, _company_e1 = await seed_uploader(dsns, slug="ilex")
    company_e2 = await seed_company(dsns["admin"], tenant_id=tenant_id, name="E2", cif="B06183446")
    # Sube el fichero a E2 como tenant_admin (autorizado a subir a cualquier empresa de su tenant).
    admin_email = "admin-hermana@ilex.es"
    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email=admin_email,
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    admin_token = await token_for(client, email=admin_email)
    file_e2 = await _upload_and_get_file_id(client, admin_token, company_e2)

    empleado_token = await token_for(client, email="ana@ilex.es")
    resp = await client.get(download_url_path(file_e2), headers=auth(empleado_token))

    assert resp.status_code == 403, resp.text


async def test_c4_descargar_fichero_de_otro_tenant_da_404(authapi: Api) -> None:
    """C4: fichero de otro tenant -> 404 (invisible en el contexto)."""
    client, dsns = authapi
    _tenant_id, _user_id, _company_id = await seed_uploader(dsns, slug="ilex")
    token = await token_for(client, email="ana@ilex.es")

    tid_otra = await seed_tenant(dsns["admin"], "otra-dl", "Otra Descarga")
    comp_otra = await seed_company(dsns["admin"], tenant_id=tid_otra, name="EO", cif="A39031620")
    user_otra = await seed_user(
        dsns["admin"],
        tenant_id=tid_otra,
        email="bob@otra.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    file_otra = await seed_uploaded_file(
        dsns, tenant_id=tid_otra, company_id=comp_otra, uploaded_by=user_otra
    )

    resp = await client.get(download_url_path(file_otra), headers=auth(token))

    assert resp.status_code == 404, resp.text


async def test_c5_sin_autenticar_no_hay_descarga(authapi: Api) -> None:
    """C5: sin token válido -> 401."""
    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    file_id = await _upload_and_get_file_id(client, token, company_id)

    resp = await client.get(download_url_path(file_id), headers={"Host": "ilex.localhost"})

    assert resp.status_code == 401, resp.text


async def test_c6_fichero_inexistente_da_404(authapi: Api) -> None:
    """C6: `file_id` que no existe en ningún tenant -> 404."""
    from uuid import uuid4  # noqa: PLC0415

    client, dsns = authapi
    await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    resp = await client.get(download_url_path(str(uuid4())), headers=auth(token))

    assert resp.status_code == 404, resp.text


async def test_c8_bucket_de_minio_no_es_accesible_sin_firma(authapi: Api) -> None:
    """C8 (anti-cruce v2): un GET directo a MinIO sin la query de firma no descarga nada."""
    from invoice_intake import storage  # noqa: PLC0415

    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    file_id = await _upload_and_get_file_id(client, token, company_id)

    bucket = storage.bucket_for(tenant_id)
    resp_meta = await client.get(download_url_path(file_id), headers=auth(token))
    key = httpx.URL(resp_meta.json()["url"]).path.removeprefix(f"/{bucket}/")

    async with httpx.AsyncClient() as raw:
        download = await raw.get(_minio_object_url(bucket, key))
    assert download.status_code != 200
    assert download.content != JPEG

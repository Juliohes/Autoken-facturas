"""Tests de comportamiento: descarga de fichero vía proxy de la API (2026-08-01).

Reemplaza a `download-url` (S2.7) como camino real del botón "Ver" del panel: en el despliegue
real, MinIO nunca se expone públicamente (aislamiento por tenant, ADR-0015), así que una URL
firmada de MinIO es inalcanzable desde el navegador — ver docstring de
`invoice_intake.service.get_download_bytes`. Mismos criterios de autorización que
`test_intake_download.py` (S2.7), observados aquí sobre el endpoint nuevo.
"""

from __future__ import annotations

from uuid import uuid4

import httpx

from tests._auth import USER_PASSWORD_HASH
from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._intake import JPEG, JPEG_CT, auth, seed_uploader, token_for, upload_parts
from tests._ocr import seed_uploaded_file

Api = tuple[httpx.AsyncClient, dict[str, str]]

UPLOADS = "/api/v1/uploads"


def image_path(file_id: str) -> str:
    return f"{UPLOADS}/{file_id}/image"


async def _upload_and_get_file_id(client: httpx.AsyncClient, token: str, company_id: str) -> str:
    resp = await client.post(
        UPLOADS,
        headers=auth(token),
        **upload_parts(JPEG, company_id, filename="f.jpg", content_type=JPEG_CT),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_c1_ver_el_fichero_propio_devuelve_los_bytes_originales(authapi: Api) -> None:
    """C1: los bytes que llegan son EXACTAMENTE los subidos, con el content-type real."""
    client, dsns = authapi
    _tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    file_id = await _upload_and_get_file_id(client, token, company_id)

    resp = await client.get(image_path(file_id), headers=auth(token))

    assert resp.status_code == 200, resp.text
    assert resp.content == JPEG
    assert resp.headers["content-type"] == JPEG_CT


async def test_c2_ver_fichero_de_empresa_hermana_da_403(authapi: Api) -> None:
    """C2: fichero de otra empresa del mismo tenant -> 403."""
    client, dsns = authapi
    tenant_id, _user_id, _company_e1 = await seed_uploader(dsns, slug="ilex")
    company_e2 = await seed_company(dsns["admin"], tenant_id=tenant_id, name="E2", cif="B06183446")
    admin_email = "admin-hermana-img@ilex.es"
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
    resp = await client.get(image_path(file_e2), headers=auth(empleado_token))

    assert resp.status_code == 403, resp.text


async def test_c3_ver_fichero_de_otro_tenant_da_404(authapi: Api) -> None:
    """C3: fichero de otro tenant -> 404 (invisible en el contexto)."""
    client, dsns = authapi
    _tenant_id, _user_id, _company_id = await seed_uploader(dsns, slug="ilex")
    token = await token_for(client, email="ana@ilex.es")

    tid_otra = await seed_tenant(dsns["admin"], "otra-img", "Otra Imagen")
    comp_otra = await seed_company(dsns["admin"], tenant_id=tid_otra, name="EO", cif="A39031620")
    user_otra = await seed_user(
        dsns["admin"],
        tenant_id=tid_otra,
        email="bob-img@otra.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    file_otra = await seed_uploaded_file(
        dsns, tenant_id=tid_otra, company_id=comp_otra, uploaded_by=user_otra
    )

    resp = await client.get(image_path(file_otra), headers=auth(token))

    assert resp.status_code == 404, resp.text


async def test_c4_sin_autenticar_no_se_ve_la_imagen(authapi: Api) -> None:
    """C4: sin token válido -> 401."""
    client, dsns = authapi
    _tenant_id, _user_id, company_id = await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")
    file_id = await _upload_and_get_file_id(client, token, company_id)

    resp = await client.get(image_path(file_id), headers={"Host": "ilex.localhost"})

    assert resp.status_code == 401, resp.text


async def test_c5_fichero_inexistente_da_404(authapi: Api) -> None:
    """C5: `file_id` que no existe en ningún tenant -> 404."""
    client, dsns = authapi
    await seed_uploader(dsns)
    token = await token_for(client, email="ana@ilex.es")

    resp = await client.get(image_path(str(uuid4())), headers=auth(token))

    assert resp.status_code == 404, resp.text


async def test_c6_un_user_no_ve_la_foto_de_un_companero_de_la_misma_empresa(
    authapi: Api,
) -> None:
    """C6 (cumplimiento, 2026-08-02): dos `user` de la MISMA empresa -> cada uno solo ve lo que
    subió él mismo, aunque la RLS (tenant+empresa) los deje pasar a ambos. Julio lo pidió de forma
    explícita: ningún `user` debe poder ver, de ninguna manera, la foto de otro."""
    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns, slug="ilex")
    ana_token = await token_for(client, email="ana@ilex.es")
    file_ana = await _upload_and_get_file_id(client, ana_token, company_id)

    bob = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="bob-companero-img@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    from tests._intake import seed_membership  # noqa: PLC0415

    await seed_membership(dsns["admin"], user_id=bob, company_id=company_id, tenant_id=tenant_id)
    bob_token = await token_for(client, email="bob-companero-img@ilex.es")

    resp = await client.get(image_path(file_ana), headers=auth(bob_token))

    assert resp.status_code == 403, resp.text


async def test_c7_un_tenant_admin_si_ve_cualquier_foto_de_su_asesoria(authapi: Api) -> None:
    """C7 (regresión): a diferencia de C6, un `tenant_admin` conserva la visión completa de su
    asesoría (es quien revisa el trabajo de todos los `user`, no un compañero más)."""
    client, dsns = authapi
    tenant_id, _user_id, company_id = await seed_uploader(dsns, slug="ilex")
    ana_token = await token_for(client, email="ana@ilex.es")
    file_ana = await _upload_and_get_file_id(client, ana_token, company_id)

    admin_email = "admin-ve-todo-img@ilex.es"
    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email=admin_email,
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    admin_token = await token_for(client, email=admin_email)

    resp = await client.get(image_path(file_ana), headers=auth(admin_token))

    assert resp.status_code == 200, resp.text
    assert resp.content == JPEG

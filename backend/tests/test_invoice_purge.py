"""Tests de comportamiento S3.5: purga de facturas de prueba (spec docs/specs/S3.5).

Criterios C1-C8 (backend). Observable vía HTTP (cliente ASGI con `Host` de tenant), autenticado
como `tenant_admin`, contra Postgres y MinIO reales.
"""

from __future__ import annotations

import httpx

from invoice_intake import storage
from tests._auth import USER_PASSWORD_HASH
from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._intake import JPEG, audit_entries, object_exists, seed_tenant_admin, token_for
from tests._invoicing import (
    auth,
    fetch_invoice_by_id,
    fetch_invoice_edits,
    fetch_tax_lines,
    fetch_uploaded_file,
    seed_invoice,
)
from tests._ocr import seed_uploaded_file, seed_uploaded_file_page

Api = tuple[httpx.AsyncClient, dict[str, str]]

URL = "/api/v1/invoices/test/purge"


async def _company_for(dsns: dict[str, str], *, tenant_id: str, cif: str = "A39031620") -> str:
    return await seed_company(dsns["admin"], tenant_id=tenant_id, name="Empresa", cif=cif)


async def test_c1_purgar_borra_todas_las_facturas_de_prueba_y_deja_las_reales(
    authapi: Api,
) -> None:
    """C1: 2 de prueba (dos empresas) + 1 real -> purged=2; la real sigue intacta."""
    client, dsns = authapi
    tenant_id, _ = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    company_1 = await _company_for(dsns, tenant_id=tenant_id, cif="A39031620")
    company_2 = await _company_for(dsns, tenant_id=tenant_id, cif="B06183446")
    test_1 = await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_1, is_test=True)
    test_2 = await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_2, is_test=True)
    real = await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_1, is_test=False)
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.post(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"purged": 2}
    assert await fetch_invoice_by_id(dsns, invoice_id=test_1) is None
    assert await fetch_invoice_by_id(dsns, invoice_id=test_2) is None
    assert await fetch_invoice_by_id(dsns, invoice_id=real) is not None


async def test_c2_purgar_borra_tramos_de_iva_y_ediciones_de_la_factura_purgada(
    authapi: Api,
) -> None:
    """C2: al purgar, sus `invoice_tax_lines`/`invoice_edits` desaparecen también (cascada)."""
    client, dsns = authapi
    tenant_id, _ = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    company_id = await _company_for(dsns, tenant_id=tenant_id)
    invoice_id = await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        is_test=True,
        tax_lines=[{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}],
    )
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.post(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert await fetch_tax_lines(dsns, invoice_id=invoice_id) == []
    assert await fetch_invoice_edits(dsns, invoice_id=invoice_id) == []


async def test_c3_purgar_borra_el_fichero_subido_y_su_objeto_en_minio(authapi: Api) -> None:
    """C3: la fila de `uploaded_files` y el objeto en MinIO desaparecen tras purgar."""
    client, dsns = authapi
    tenant_id, _ = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    company_id = await _company_for(dsns, tenant_id=tenant_id)
    invoice_id = await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, is_test=True)
    invoice = await fetch_invoice_by_id(dsns, invoice_id=invoice_id)
    assert invoice is not None
    file_id = str(invoice["uploaded_file_id"])
    uploaded = await fetch_uploaded_file(dsns, file_id=file_id)
    assert uploaded is not None
    assert await object_exists(
        dsns, tenant_id=tenant_id, company_id=company_id, sha256=uploaded["sha256"]
    )
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.post(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert await fetch_uploaded_file(dsns, file_id=file_id) is None
    assert not await object_exists(
        dsns, tenant_id=tenant_id, company_id=company_id, sha256=uploaded["sha256"]
    )


async def test_purgar_un_documento_multipagina_borra_las_paginas_secundarias_en_minio(
    authapi: Api,
) -> None:
    """La cascada SQL borra las filas y la limpieza post-commit recibe todo el lote."""
    client, dsns = authapi
    tenant_id, admin_id = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    company_id = await _company_for(dsns, tenant_id=tenant_id)
    root_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=admin_id,
        content=JPEG + b"-root-purge-pages",
        status="confirmed",
    )
    page_bucket, page_key = await seed_uploaded_file_page(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        root_uploaded_file_id=root_id,
        page_number=2,
        content=JPEG + b"-page-purge-pages",
    )
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        is_test=True,
        confirmed_by=admin_id,
        uploaded_file_id=root_id,
    )
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    response = await client.post(URL, headers=auth(token, "ilex.localhost"))

    assert response.status_code == 200, response.text
    assert not storage.object_exists(page_bucket, page_key)


async def test_c4_purgar_deja_una_entrada_de_auditoria_por_factura(authapi: Api) -> None:
    """C4: 2 facturas de prueba purgadas -> 2 entradas `invoice.purge_test`, una por factura."""
    client, dsns = authapi
    tenant_id, _ = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    company_id = await _company_for(dsns, tenant_id=tenant_id)
    invoice_1 = await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, is_test=True)
    invoice_2 = await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, is_test=True)
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.post(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert await audit_entries(dsns, action="invoice.purge_test", entity_id=invoice_1) == 1
    assert await audit_entries(dsns, action="invoice.purge_test", entity_id=invoice_2) == 1


async def test_c5_sin_facturas_de_prueba_la_purga_no_falla(authapi: Api) -> None:
    """C5: asesoría sin facturas de prueba -> 200, `{"purged": 0}`, no es un error."""
    client, dsns = authapi
    tenant_id, _ = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    company_id = await _company_for(dsns, tenant_id=tenant_id)
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, is_test=False)
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.post(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"purged": 0}


async def test_c6_anticruce_purgar_no_toca_facturas_de_prueba_de_otro_tenant(
    authapi: Api,
) -> None:
    """C6: purgar en `ilex` no borra las facturas de prueba de `otra` (RLS)."""
    client, dsns = authapi
    tenant_ilex, _ = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    tenant_otra, _ = await seed_tenant_admin(dsns, slug="otra", email="admin@otra.es")
    company_ilex = await _company_for(dsns, tenant_id=tenant_ilex, cif="A39031620")
    company_otra = await _company_for(dsns, tenant_id=tenant_otra, cif="B06183446")
    await seed_invoice(dsns, tenant_id=tenant_ilex, company_id=company_ilex, is_test=True)
    invoice_otra = await seed_invoice(
        dsns, tenant_id=tenant_otra, company_id=company_otra, is_test=True
    )
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.post(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"purged": 1}
    assert await fetch_invoice_by_id(dsns, invoice_id=invoice_otra) is not None


async def test_c7_un_empleado_no_puede_purgar(authapi: Api) -> None:
    """C7: `user` (no `tenant_admin`) -> 403; nada se borra."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="empleado@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    company_id = await _company_for(dsns, tenant_id=tenant_id)
    invoice_id = await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, is_test=True)
    token = await token_for(client, email="empleado@ilex.es", hostname="ilex.localhost")

    resp = await client.post(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 403
    assert await fetch_invoice_by_id(dsns, invoice_id=invoice_id) is not None


async def test_c8_sin_autenticar_no_hay_purga(authapi: Api) -> None:
    """C8: sin token válido -> 401."""
    client, _dsns = authapi

    resp = await client.post(URL, headers=auth("token-invalido", "ilex.localhost"))

    assert resp.status_code == 401

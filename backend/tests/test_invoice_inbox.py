"""Pruebas de comportamiento de la bandeja privada R-020."""

from __future__ import annotations

import asyncpg

from tests._auth import USER_PASSWORD_HASH
from tests._dbtest import seed_company, seed_membership, seed_tenant, seed_user
from tests._intake import auth, token_for
from tests._ocr import JPEG, seed_uploaded_file, seed_uploaded_file_page


async def _seed_inbox(dsns: dict[str, str]) -> dict[str, str]:
    tenant_id = await seed_tenant(dsns["admin"], "inbox", "Inbox Asesoría")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Inbox Empresa", cif="A39031620"
    )
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="uno@inbox.es",
        password_hash=USER_PASSWORD_HASH,
    )
    other_user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="dos@inbox.es",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(
        dsns["admin"], user_id=user_id, company_id=company_id, tenant_id=tenant_id
    )
    await seed_membership(
        dsns["admin"], user_id=other_user_id, company_id=company_id, tenant_id=tenant_id
    )
    own_file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=user_id,
        content=JPEG + b"-own",
        status="processing",
    )
    await seed_uploaded_file_page(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        root_uploaded_file_id=own_file_id,
        page_number=2,
        content=JPEG + b"-own-page-2",
    )
    other_file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=other_user_id,
        content=JPEG + b"-other",
        status="needs_review",
    )
    return {
        "tenant_id": tenant_id,
        "company_id": company_id,
        "user_id": user_id,
        "other_user_id": other_user_id,
        "own_file_id": own_file_id,
        "other_file_id": other_file_id,
    }


async def test_inbox_es_self_only_no_expone_pii_y_calcula_paginas(authapi) -> None:
    """Un user ve solo sus documentos, incluso compartiendo empresa con otro user."""
    client, dsns = authapi
    seeded = await _seed_inbox(dsns)
    token = await token_for(client, email="uno@inbox.es", hostname="inbox.localhost")

    response = await client.get("/api/v1/invoices/inbox", headers=auth(token, "inbox.localhost"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["items"]] == [seeded["own_file_id"]]
    assert body["items"][0]["status"] == "processing"
    assert body["items"][0]["page_count"] == 2
    assert body["items"][0]["capture_session_id"] is None
    assert body["items"][0]["capture_sequence"] is None
    assert body["items"][0]["draft_updated_at"] is None
    assert body["summary"] == {"processing": 1, "ready": 0, "attention": 0}
    assert body["next_cursor"] is None
    assert (
        not {
            "counterparty_tax_id",
            "counterparty_name",
            "invoice_number",
            "total_amount",
            "raw",
        }
        & body.keys()
    )


async def test_inbox_tenant_admin_tambien_ve_solo_sus_subidas(authapi) -> None:
    """El rol tenant_admin no convierte la bandeja personal en supervisión del tenant."""
    client, dsns = authapi
    seeded = await _seed_inbox(dsns)
    admin_id = await seed_user(
        dsns["admin"],
        tenant_id=seeded["tenant_id"],
        email="admin@inbox.es",
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    admin_file_id = await seed_uploaded_file(
        dsns,
        tenant_id=seeded["tenant_id"],
        company_id=seeded["company_id"],
        uploaded_by=admin_id,
        content=JPEG + b"-admin",
        status="ocr_done",
    )
    token = await token_for(client, email="admin@inbox.es", hostname="inbox.localhost")

    response = await client.get("/api/v1/invoices/inbox", headers=auth(token, "inbox.localhost"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["items"]] == [admin_file_id]
    assert body["summary"] == {"processing": 0, "ready": 1, "attention": 0}


async def test_inbox_usa_cursor_compuesto_y_orden_estable(authapi) -> None:
    """La segunda página continúa después del último `(created_at, id)` de la primera."""
    client, dsns = authapi
    seeded = await _seed_inbox(dsns)
    await seed_uploaded_file(
        dsns,
        tenant_id=seeded["tenant_id"],
        company_id=seeded["company_id"],
        uploaded_by=seeded["user_id"],
        content=JPEG + b"-own-second",
        status="processing",
    )
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "UPDATE uploaded_files SET created_at = now() - interval '1 hour' WHERE id = $1",
            seeded["own_file_id"],
        )
    finally:
        await conn.close()
    token = await token_for(client, email="uno@inbox.es", hostname="inbox.localhost")

    first = await client.get(
        "/api/v1/invoices/inbox?limit=1", headers=auth(token, "inbox.localhost")
    )
    assert first.status_code == 200, first.text
    assert len(first.json()["items"]) == 1
    assert first.json()["next_cursor"] is not None

    second = await client.get(
        f"/api/v1/invoices/inbox?limit=1&cursor={first.json()['next_cursor']}",
        headers=auth(token, "inbox.localhost"),
    )
    assert second.status_code == 200, second.text
    assert len(second.json()["items"]) == 1
    assert second.json()["items"][0]["id"] != first.json()["items"][0]["id"]
    assert second.json()["next_cursor"] is None


async def test_inbox_rechaza_cursor_corrupto_sin_consultar_datos(authapi) -> None:
    """Un cursor manipulado no se interpreta como una posición válida."""
    client, dsns = authapi
    await _seed_inbox(dsns)
    token = await token_for(client, email="uno@inbox.es", hostname="inbox.localhost")

    response = await client.get(
        "/api/v1/invoices/inbox?cursor=no-es-un-cursor",
        headers=auth(token, "inbox.localhost"),
    )

    assert response.status_code == 422

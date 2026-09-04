"""Pruebas de comportamiento de borradores de revisión R-021/R-022."""

from __future__ import annotations

import json

import asyncpg

from tests._auth import USER_PASSWORD_HASH
from tests._dbtest import seed_company, seed_membership, seed_tenant, seed_user
from tests._intake import auth, token_for
from tests._ocr import JPEG, seed_uploaded_file


async def _seed_draft(dsns: dict[str, str]) -> dict[str, str]:
    tenant_id = await seed_tenant(dsns["admin"], "drafts", "Draft Asesoría")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Draft Empresa", cif="A39031620"
    )
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="draft@drafts.es",
        password_hash=USER_PASSWORD_HASH,
    )
    other_user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="other@drafts.es",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(
        dsns["admin"], user_id=user_id, company_id=company_id, tenant_id=tenant_id
    )
    await seed_membership(
        dsns["admin"], user_id=other_user_id, company_id=company_id, tenant_id=tenant_id
    )
    file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=user_id,
        content=JPEG + b"-draft",
        status="needs_review",
    )
    other_file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=other_user_id,
        content=JPEG + b"-other-draft",
        status="needs_review",
    )
    return {
        "tenant_id": tenant_id,
        "company_id": company_id,
        "user_id": user_id,
        "file_id": file_id,
        "other_file_id": other_file_id,
    }


def _body(revision: int = 0, *, total_amount: str = "121.00") -> dict[str, object]:
    return {
        "revision": revision,
        "direction": "recibida",
        "issue_date": "2026-08-21",
        "invoice_number": "F-123",
        "counterparty_tax_id": "B12345678",
        "counterparty_name": "Proveedor Draft",
        "net_amount": "100.00",
        "tax_amount": "21.00",
        "total_amount": total_amount,
        "irpf_amount": None,
        "tax_lines": [{"iva_pct": "21.00", "base": "100.00", "cuota": "21.00"}],
    }


async def test_put_draft_guarda_snapshot_cifrado_y_asigna_revision(authapi) -> None:
    client, dsns = authapi
    seeded = await _seed_draft(dsns)
    token = await token_for(client, email="draft@drafts.es", hostname="drafts.localhost")

    response = await client.put(
        f"/api/v1/uploads/{seeded['file_id']}/draft",
        json=_body(),
        headers=auth(token, "drafts.localhost"),
    )

    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1
    assert response.json()["updated_at"]

    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "SELECT revision, counterparty_tax_id, counterparty_tax_id_blind_index, tax_lines "
            "FROM review_drafts WHERE uploaded_file_id = $1",
            seeded["file_id"],
        )
    finally:
        await conn.close()
    assert row["revision"] == 1
    assert row["counterparty_tax_id"] is not None
    assert bytes(row["counterparty_tax_id"]) != b"B12345678"
    assert row["counterparty_tax_id_blind_index"]
    assert json.loads(row["tax_lines"]) == [
        {"iva_pct": "21.00", "base": "100.00", "cuota": "21.00"}
    ]


async def test_put_draft_rechaza_revision_obsoleta_y_conserva_el_ultimo_snapshot(authapi) -> None:
    client, dsns = authapi
    seeded = await _seed_draft(dsns)
    token = await token_for(client, email="draft@drafts.es", hostname="drafts.localhost")
    url = f"/api/v1/uploads/{seeded['file_id']}/draft"
    headers = auth(token, "drafts.localhost")

    first = await client.put(url, json=_body(), headers=headers)
    second = await client.put(url, json=_body(1, total_amount="122.00"), headers=headers)
    stale = await client.put(url, json=_body(1, total_amount="999.00"), headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["revision"] == 2
    assert stale.status_code == 409
    assert stale.json()["detail"] == {"code": "draft_revision_conflict", "current_revision": 2}

    conn = await asyncpg.connect(dsns["admin"])
    try:
        total = await conn.fetchval(
            "SELECT total_amount FROM review_drafts WHERE uploaded_file_id = $1",
            seeded["file_id"],
        )
    finally:
        await conn.close()
    assert str(total) == "122.00"


async def test_put_draft_es_privado_y_no_permite_guardar_fichero_de_otro_usuario(authapi) -> None:
    client, dsns = authapi
    seeded = await _seed_draft(dsns)
    token = await token_for(client, email="draft@drafts.es", hostname="drafts.localhost")

    response = await client.put(
        f"/api/v1/uploads/{seeded['other_file_id']}/draft",
        json=_body(),
        headers=auth(token, "drafts.localhost"),
    )

    assert response.status_code == 404

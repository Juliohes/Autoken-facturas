"""Pruebas de comportamiento de la supervisión read-only R-026."""

from __future__ import annotations

from tests._auth import USER_PASSWORD_HASH
from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._intake import auth, token_for
from tests._ocr import JPEG, seed_uploaded_file, seed_uploaded_file_page


async def _seed_supervision(dsns: dict[str, str]) -> dict[str, str]:
    tenant_id = await seed_tenant(dsns["admin"], "supervision", "Supervisión Asesoría")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Supervisión Empresa", cif="A39031620"
    )
    admin_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="admin@supervision.es",
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    worker_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="alice@supervision.es",
        password_hash=USER_PASSWORD_HASH,
    )
    own_file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=admin_id,
        content=JPEG + b"-admin",
        status="needs_review",
    )
    pending_file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=worker_id,
        content=JPEG + b"-alice-pending",
        status="needs_review",
    )
    confirmed_file_id = await seed_uploaded_file(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        uploaded_by=worker_id,
        content=JPEG + b"-alice-confirmed",
        status="confirmed",
    )
    await seed_uploaded_file_page(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        root_uploaded_file_id=pending_file_id,
        page_number=2,
        content=JPEG + b"-alice-page-2",
    )
    return {
        "tenant_id": tenant_id,
        "company_id": company_id,
        "admin_id": admin_id,
        "own_file_id": own_file_id,
        "pending_file_id": pending_file_id,
        "confirmed_file_id": confirmed_file_id,
    }


async def test_supervision_solo_muestra_pendientes_ajenos_con_metadata(authapi) -> None:
    client, dsns = authapi
    seeded = await _seed_supervision(dsns)
    token = await token_for(client, email="admin@supervision.es", hostname="supervision.localhost")

    response = await client.get(
        "/api/v1/invoices/pending-supervision",
        headers=auth(token, "supervision.localhost"),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["items"]] == [seeded["pending_file_id"]]
    assert body["items"][0]["user_email"] == "alice@supervision.es"
    assert body["items"][0]["company_name"] == "Supervisión Empresa"
    assert body["items"][0]["page_count"] == 2
    assert body["next_cursor"] is None


async def test_supervision_user_no_tiene_acceso_y_review_readonly_no_expone_acciones(
    authapi,
) -> None:
    client, dsns = authapi
    seeded = await _seed_supervision(dsns)
    token = await token_for(client, email="admin@supervision.es", hostname="supervision.localhost")

    readonly = await client.get(
        f"/api/v1/uploads/{seeded['pending_file_id']}/review-readonly",
        headers=auth(token, "supervision.localhost"),
    )

    assert readonly.status_code == 409  # no hay OCR sembrado para abrir datos de revisión

    worker_token = await token_for(
        client, email="alice@supervision.es", hostname="supervision.localhost"
    )
    denied = await client.get(
        "/api/v1/invoices/pending-supervision",
        headers=auth(worker_token, "supervision.localhost"),
    )
    assert denied.status_code == 403


async def test_tenant_admin_no_puede_guardar_borrador_de_pendiente_ajena(authapi) -> None:
    """Administrar el tenant no convierte al administrador en dueño del borrador ajeno."""
    client, dsns = authapi
    seeded = await _seed_supervision(dsns)
    token = await token_for(client, email="admin@supervision.es", hostname="supervision.localhost")

    response = await client.put(
        f"/api/v1/uploads/{seeded['pending_file_id']}/draft",
        json={
            "revision": 0,
            "direction": "recibida",
            "issue_date": "2026-08-22",
            "invoice_number": "AJENA-1",
            "counterparty_tax_id": "B12345678",
            "counterparty_name": "Proveedor ajeno",
            "net_amount": "100.00",
            "tax_amount": "21.00",
            "total_amount": "121.00",
            "irpf_amount": None,
            "tax_lines": [],
        },
        headers=auth(token, "supervision.localhost"),
    )

    assert response.status_code == 403

    retry = await client.post(
        f"/api/v1/uploads/{seeded['pending_file_id']}/retry-ocr",
        headers=auth(token, "supervision.localhost"),
    )

    assert retry.status_code == 403

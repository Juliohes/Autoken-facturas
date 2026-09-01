"""Tests de comportamiento R-052: ciclo de vida de pendientes y duplicados.

La fase roja fija el contrato HTTP antes de implementar las nuevas operaciones de dominio.
"""

from __future__ import annotations

from tests._invoicing import auth, confirm_body, confirm_url, seed_confirmable, seed_extraction
from tests._ocr import seed_uploaded_file


async def test_c5_eliminar_factura_pendiente_propietaria_borra_el_documento(authapi) -> None:
    # spec: C5
    client, _dsns = authapi
    data = await seed_confirmable(client=client, dsns=_dsns, file_status="needs_review")

    response = await client.delete(
        f"/api/v1/uploads/{data['file_id']}",
        headers=auth(data["token"]),
    )

    assert response.status_code == 204, response.text


async def test_c7_factura_confirmada_no_se_puede_eliminar(authapi) -> None:
    # spec: C7
    client, _dsns = authapi
    data = await seed_confirmable(client=client, dsns=_dsns, file_status="confirmed")

    response = await client.delete(
        f"/api/v1/uploads/{data['file_id']}",
        headers=auth(data["token"]),
    )

    assert response.status_code == 409, response.text


async def test_c10_revision_bloquea_una_factura_con_numero_cif_e_importe_repetidos(authapi) -> None:
    # spec: C10
    client, dsns = authapi
    original = await seed_confirmable(
        dsns,
        client,
        invoice_number="R052-1",
        counterparty_cif="A39031620",
    )
    confirmed = await client.post(
        confirm_url(original["file_id"]),
        headers=auth(original["token"]),
        json=confirm_body(invoice_number="R052-1"),
    )
    assert confirmed.status_code == 201, confirmed.text

    duplicate_file = await seed_uploaded_file(
        dsns,
        tenant_id=original["tenant_id"],
        company_id=original["company_id"],
        uploaded_by=original["user_id"],
        content=b"r052-different-photo",
        status="needs_review",
    )
    await seed_extraction(
        dsns,
        file_id=duplicate_file,
        tenant_id=original["tenant_id"],
        company_id=original["company_id"],
        counterparty_tax_id="A39031620",
        invoice_number="R052-1",
        total="121.00",
    )

    review = await client.get(
        f"/api/v1/uploads/{duplicate_file}/review",
        headers=auth(original["token"]),
    )

    assert review.status_code == 200, review.text
    body = review.json()
    assert body["duplicate"]["kind"] == "confirmed"
    assert "duplicate_invoice" in body["blocking_reasons"]

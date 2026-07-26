"""Tests de comportamiento S3.3: edición auditada de una factura confirmada (spec docs/specs/S3.3).

Criterios C1-C11. Observable vía HTTP (cliente ASGI con `Host` de tenant), autenticado como
`tenant_admin`, contra Postgres real con una factura confirmada ya sembrada (`seed_invoice`,
S2.6/S3.1). Fase roja: el endpoint `PATCH /invoices/{invoice_id}` aún no existe.
"""

from __future__ import annotations

from uuid import uuid4

import httpx

from tests._invoicing import (
    COUNTERPARTY_CIF,
    INVALID_CIF,
    OWN_CIF,
    auth,
    fetch_invoice_by_id,
    fetch_invoice_edits,
    fetch_tax_lines,
    seed_invoice,
)
from tests._reporting import seed_admin_with_company

Api = tuple[httpx.AsyncClient, dict[str, str]]


def edit_url(invoice_id: str) -> str:
    return f"/api/v1/invoices/{invoice_id}"


async def _seed_confirmed_invoice(dsns, client, **kwargs):
    """Siembra un `tenant_admin` con una empresa y una factura confirmada de esa empresa.

    Devuelve (tenant_id, admin_id, company_id, token, invoice_id).
    """
    tenant_id, admin_id, company_id, token = await seed_admin_with_company(dsns, client)
    invoice_id = await seed_invoice(
        dsns, tenant_id=tenant_id, company_id=company_id, confirmed_by=admin_id, **kwargs
    )
    return tenant_id, admin_id, company_id, token, invoice_id


async def test_c1_editar_un_campo_simple_lo_cambia_y_registra_el_valor_anterior(
    authapi: Api,
) -> None:
    """C1: editar total_amount lo cambia; invoice_edits guarda el valor anterior y el nuevo."""
    client, dsns = authapi
    _tenant_id, admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, total_amount="121.00"
    )

    resp = await client.patch(
        edit_url(invoice_id), headers=auth(token, "ilex.localhost"), json={"total_amount": "150.00"}
    )

    assert resp.status_code == 200, resp.text
    invoice = await fetch_invoice_by_id(dsns, invoice_id=invoice_id)
    assert str(invoice["total_amount"]) == "150.00"

    edits = await fetch_invoice_edits(dsns, invoice_id=invoice_id)
    assert len(edits) == 1
    assert edits[0]["field"] == "total_amount"
    assert edits[0]["old_value"] == "121.00"
    assert edits[0]["new_value"] == "150.00"
    assert str(edits[0]["edited_by"]) == admin_id


async def test_c2_editar_varios_campos_deja_una_fila_por_campo(authapi: Api) -> None:
    """C2: editar issue_date y net_amount deja exactamente 2 filas en invoice_edits."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, issue_date="2026-05-10", net_amount="100.00"
    )

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={"issue_date": "2026-06-01", "net_amount": "90.00"},
    )

    assert resp.status_code == 200, resp.text
    edits = await fetch_invoice_edits(dsns, invoice_id=invoice_id)
    fields = {e["field"] for e in edits}
    assert fields == {"issue_date", "net_amount"}
    assert len(edits) == 2


async def test_c3_campo_enviado_igual_al_actual_no_genera_fila(authapi: Api) -> None:
    """C3: enviar total_amount igual al actual no crea fila; net_amount sí cambia y sí la crea."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, total_amount="121.00", net_amount="100.00"
    )

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={"total_amount": "121.00", "net_amount": "90.00"},
    )

    assert resp.status_code == 200, resp.text
    edits = await fetch_invoice_edits(dsns, invoice_id=invoice_id)
    assert len(edits) == 1
    assert edits[0]["field"] == "net_amount"


async def test_c4_cif_de_contraparte_invalido_bloquea_la_edicion(authapi: Api) -> None:
    """C4: cambiar counterparty_tax_id a uno inválido -> 422; nada cambia, sin filas de edición."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, counterparty_tax_id=COUNTERPARTY_CIF, total_amount="121.00"
    )

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={"counterparty_tax_id": INVALID_CIF, "total_amount": "999.00"},
    )

    assert resp.status_code == 422, resp.text
    invoice = await fetch_invoice_by_id(dsns, invoice_id=invoice_id)
    assert invoice["counterparty_tax_id"] == COUNTERPARTY_CIF
    assert str(invoice["total_amount"]) == "121.00"
    assert await fetch_invoice_edits(dsns, invoice_id=invoice_id) == []


async def test_c4b_cambiar_el_cif_sin_el_nombre_se_rechaza(authapi: Api) -> None:
    """Hallazgo de auditoría: cambiar solo counterparty_tax_id (sin nombre en el mismo PATCH)
    dejaría el CIF nuevo verificado contra el nombre VIEJO -> se rechaza explícitamente (422)."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, counterparty_tax_id=COUNTERPARTY_CIF, counterparty_name="Prov SA"
    )

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={"counterparty_tax_id": OWN_CIF},  # sin counterparty_name
    )

    assert resp.status_code == 422, resp.text
    invoice = await fetch_invoice_by_id(dsns, invoice_id=invoice_id)
    assert invoice["counterparty_tax_id"] == COUNTERPARTY_CIF  # no cambió
    assert await fetch_invoice_edits(dsns, invoice_id=invoice_id) == []


async def test_c5_cambiar_a_un_cif_valido_actualiza_el_estado_del_cif(authapi: Api) -> None:
    """C5: cambiar a otro CIF resoluble y válido -> 200, counterparty_cif_status queda "valid"."""
    from tests._counterparty import seed_counterparty  # noqa: PLC0415

    client, dsns = authapi
    tenant_id, _admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, counterparty_tax_id=COUNTERPARTY_CIF
    )
    await seed_counterparty(dsns, tenant_id=tenant_id, cif=OWN_CIF, name="Otro Proveedor SA")

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={"counterparty_tax_id": OWN_CIF, "counterparty_name": "Otro Proveedor SA"},
    )

    assert resp.status_code == 200, resp.text
    invoice = await fetch_invoice_by_id(dsns, invoice_id=invoice_id)
    assert invoice["counterparty_tax_id"] == OWN_CIF
    assert invoice["counterparty_cif_status"] == "valid"


async def test_s5_2_c7_editar_un_campo_sensible_cifra_el_rastro_de_invoice_edits(
    authapi: Api,
) -> None:
    """S5.2 C7: editar el CIF/nombre de contraparte NO deja `invoice_edits.old_value`/`new_value`
    en texto plano — cifrarlos en la factura y dejarlos en claro en su auditoría sería una vía de
    fuga paralela del mismo dato que se acaba de proteger."""
    import asyncpg

    from tests._counterparty import seed_counterparty  # noqa: PLC0415
    from tests._invoicing import fetch_invoice_edits  # noqa: PLC0415

    client, dsns = authapi
    tenant_id, _admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, counterparty_tax_id=COUNTERPARTY_CIF, counterparty_name="Proveedor SA"
    )
    await seed_counterparty(dsns, tenant_id=tenant_id, cif=OWN_CIF, name="Otro Proveedor SA")

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={"counterparty_tax_id": OWN_CIF, "counterparty_name": "Otro Proveedor SA"},
    )
    assert resp.status_code == 200, resp.text

    # La fila cruda (superusuario, sin descifrar) no contiene el CIF/nombre en claro.
    conn = await asyncpg.connect(dsns["admin"])
    try:
        rows = await conn.fetch(
            "SELECT field, old_value, new_value FROM invoice_edits WHERE invoice_id = $1",
            invoice_id,
        )
    finally:
        await conn.close()
    by_field = {r["field"]: r for r in rows}
    assert COUNTERPARTY_CIF not in by_field["counterparty_tax_id"]["old_value"]
    assert OWN_CIF not in by_field["counterparty_tax_id"]["new_value"]
    assert "Proveedor SA" not in by_field["counterparty_name"]["old_value"]
    assert "Otro Proveedor SA" not in by_field["counterparty_name"]["new_value"]

    # El helper que descifra (mismo camino que usaría un export/auditoría legítima) sí recupera
    # los valores originales.
    edits = await fetch_invoice_edits(dsns, invoice_id=invoice_id)
    by_field_decrypted = {e["field"]: e for e in edits}
    assert by_field_decrypted["counterparty_tax_id"]["old_value"] == COUNTERPARTY_CIF
    assert by_field_decrypted["counterparty_tax_id"]["new_value"] == OWN_CIF
    assert by_field_decrypted["counterparty_name"]["old_value"] == "Proveedor SA"
    assert by_field_decrypted["counterparty_name"]["new_value"] == "Otro Proveedor SA"


async def test_c6_editar_tramos_de_iva_reemplaza_el_conjunto_completo(authapi: Api) -> None:
    """C6: editar tax_lines reemplaza los tramos existentes por los nuevos, no los acumula."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, tax_lines=[{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}]
    )

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={
            "tax_lines": [
                {"iva_pct": "21", "base": "50.00", "cuota": "10.50"},
                {"iva_pct": "10", "base": "50.00", "cuota": "5.00"},
            ]
        },
    )

    assert resp.status_code == 200, resp.text
    lines = await fetch_tax_lines(dsns, invoice_id=invoice_id)
    assert len(lines) == 2
    pcts = {str(line["iva_pct"]) for line in lines}
    assert pcts == {"21", "10"}

    edits = await fetch_invoice_edits(dsns, invoice_id=invoice_id)
    fields = {e["field"] for e in edits}
    # baja del tramo 21% original (base 100->50, cuota 21->10.50) + alta del tramo 10%.
    assert "tax_line[21].base" in fields
    assert "tax_line[21].cuota" in fields
    assert "tax_line[10].base" in fields
    assert "tax_line[10].cuota" in fields


async def test_c6b_tax_lines_null_explicito_no_toca_los_tramos(authapi: Api) -> None:
    """Hallazgo de auditoría: `"tax_lines": null` explícito NO es una lista de tramos válida, así
    que se trata como campo ausente (no los borra); distinto de mandar `[]` (eso sí los borra,
    spec §5)."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns,
        client,
        total_amount="121.00",
        tax_lines=[{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}],
    )

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={"total_amount": "150.00", "tax_lines": None},
    )

    assert resp.status_code == 200, resp.text
    lines = await fetch_tax_lines(dsns, invoice_id=invoice_id)
    assert len(lines) == 1  # el tramo original sigue ahí, no se ha borrado


async def test_c7_descuadre_tras_editar_avisa_no_bloquea(authapi: Api) -> None:
    """C7: una edición que deja las cifras descuadradas responde 200 y balance_ok queda false."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns,
        client,
        total_amount="121.00",
        tax_lines=[{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}],
    )

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={"total_amount": "999.00"},
    )

    assert resp.status_code == 200, resp.text
    invoice = await fetch_invoice_by_id(dsns, invoice_id=invoice_id)
    assert invoice["balance_ok"] is False


async def test_c8_solo_tenant_admin_edita(authapi: Api) -> None:
    """C8: un empleado (`user`) no puede editar -> 403."""
    from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, login  # noqa: PLC0415
    from tests._dbtest import seed_user  # noqa: PLC0415

    client, dsns = authapi
    tenant_id, _admin_id, _company_id, _token, invoice_id = await _seed_confirmed_invoice(
        dsns, client
    )
    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="empleado-edit@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    login_resp = await login(client, "ilex.localhost", "empleado-edit@ilex.es", USER_PASSWORD)
    assert login_resp.status_code == 200, login_resp.text
    empleado_token = login_resp.json()["access_token"]

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(empleado_token, "ilex.localhost"),
        json={"total_amount": "1.00"},
    )

    assert resp.status_code == 403, resp.text


async def test_c9_sin_autenticar_no_hay_edicion(authapi: Api) -> None:
    """C9: sin token válido -> 401."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, _token, invoice_id = await _seed_confirmed_invoice(
        dsns, client
    )

    resp = await client.patch(
        edit_url(invoice_id), headers={"Host": "ilex.localhost"}, json={"total_amount": "1.00"}
    )

    assert resp.status_code == 401, resp.text


async def test_c10_anti_cruce_no_se_puede_editar_factura_de_otro_tenant(authapi: Api) -> None:
    """C10: un tenant_admin de otro tenant no puede editar (id adivinado) -> 404."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, _token, invoice_id = await _seed_confirmed_invoice(
        dsns, client
    )

    _otra_tenant_id, _otra_admin, _otra_company, otra_token = await seed_admin_with_company(
        dsns, client, slug="otra-edit"
    )

    resp = await client.patch(
        edit_url(invoice_id),
        headers=auth(otra_token, "otra-edit.localhost"),
        json={"total_amount": "1.00"},
    )

    assert resp.status_code == 404, resp.text


async def test_c11_factura_inexistente_da_404(authapi: Api) -> None:
    """C11: un invoice_id que no existe en ningún tenant -> 404."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token = await seed_admin_with_company(dsns, client)

    resp = await client.patch(
        edit_url(str(uuid4())),
        headers=auth(token, "ilex.localhost"),
        json={"total_amount": "1.00"},
    )

    assert resp.status_code == 404, resp.text


async def test_c1b_patch_vacio_no_tiene_efecto(authapi: Api) -> None:
    """Caso límite (spec §5): PATCH vacío -> 200, sin filas nuevas en invoice_edits."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client
    )

    resp = await client.patch(edit_url(invoice_id), headers=auth(token, "ilex.localhost"), json={})

    assert resp.status_code == 200, resp.text
    assert await fetch_invoice_edits(dsns, invoice_id=invoice_id) == []

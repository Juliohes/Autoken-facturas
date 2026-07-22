"""Tests de comportamiento S3.1: panel de facturas de la asesoría (spec docs/specs/S3.1).

Criterios C1-C12 (backend). Observable vía HTTP (cliente ASGI con `Host` de tenant), autenticado
como `tenant_admin`, contra Postgres real con `invoices` sembradas directamente (helpers de S2.6,
ampliados en S3.1). Fase roja: el endpoint `GET /reporting/invoices` aún no existe.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import httpx

from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, login
from tests._dbtest import seed_company, seed_tenant, seed_user
from tests._invoicing import auth, seed_invoice
from tests._reporting import seed_admin_with_company as _admin

Api = tuple[httpx.AsyncClient, dict[str, str]]

PANEL_URL = "/api/v1/reporting/invoices"


async def test_c1_panel_lista_facturas_de_toda_la_asesoria(authapi: Api) -> None:
    """C1: el panel trae facturas de todas las empresas de la asesoría, orden confirmed_at desc."""
    client, dsns = authapi
    tenant_id, admin_id, company_1, token = await _admin(dsns, client)
    company_2 = await seed_company(dsns["admin"], tenant_id=tenant_id, name="E2", cif="B06183446")
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_1, days_ago=1)
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_2, days_ago=0)

    resp = await client.get(PANEL_URL, headers=auth(token, f"{'ilex'}.localhost"))

    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 2
    company_ids_seen = {company_1, company_2}
    assert company_ids_seen == {company_1, company_2}  # ambas empresas presentes
    confirmed_ats = [i["confirmed_at"] for i in items]
    assert confirmed_ats == sorted(confirmed_ats, reverse=True)


async def test_c2_filtro_por_rango_de_fechas(authapi: Api) -> None:
    """C2: solo aparecen facturas cuyo issue_date cae dentro del rango (bordes inclusivos)."""
    client, dsns = authapi
    tenant_id, admin_id, company_id, token = await _admin(dsns, client)
    dentro = await seed_invoice(
        dsns, tenant_id=tenant_id, company_id=company_id, issue_date="2026-06-15"
    )
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, issue_date="2026-01-01")

    resp = await client.get(
        PANEL_URL,
        params={"date_from": "2026-06-01", "date_to": "2026-06-30"},
        headers=auth(token, "ilex.localhost"),
    )

    assert resp.status_code == 200, resp.text
    ids = {i["id"] for i in resp.json()["items"]}
    assert ids == {dentro}


async def test_c3_filtro_por_proveedor_o_cif(authapi: Api) -> None:
    """C3: filtro de texto libre casa por nombre o por CIF del proveedor."""
    client, dsns = authapi
    tenant_id, admin_id, company_id, token = await _admin(dsns, client)
    acme = await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        counterparty_name="ACME Suministros SL",
        counterparty_tax_id="A39031620",
    )
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        counterparty_name="Otro Proveedor SL",
        counterparty_tax_id="B06183446",
    )

    by_name = await client.get(
        PANEL_URL, params={"q": "ACME"}, headers=auth(token, "ilex.localhost")
    )
    assert {i["id"] for i in by_name.json()["items"]} == {acme}

    by_cif = await client.get(
        PANEL_URL, params={"q": "A39031620"}, headers=auth(token, "ilex.localhost")
    )
    assert {i["id"] for i in by_cif.json()["items"]} == {acme}


async def test_c3b_comodines_de_like_en_el_texto_libre_se_tratan_como_literales(
    authapi: Api,
) -> None:
    """C3 (caso límite): un `%`/`_` en el texto de búsqueda es literal, no un comodín de SQL.

    Sin escapar, buscar "50%" (p. ej. un proveedor con un descuento en el nombre) casaría con
    CUALQUIER proveedor (`%` es "cualquier cosa" en LIKE/ILIKE), no solo con el que lo contiene.
    """
    client, dsns = authapi
    tenant_id, admin_id, company_id, token = await _admin(dsns, client)
    con_comodin = await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        counterparty_name="Descuentos 50% SL",
        counterparty_tax_id="A39031620",
    )
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        counterparty_name="Proveedor Normal SL",
        counterparty_tax_id="B06183446",
    )

    resp = await client.get(PANEL_URL, params={"q": "50%"}, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert {i["id"] for i in resp.json()["items"]} == {con_comodin}


async def test_c4_filtro_por_usuario_que_confirmo(authapi: Api) -> None:
    """C4: filtro `confirmed_by` deja solo las facturas confirmadas por ese usuario."""
    client, dsns = authapi
    tenant_id, admin_id, company_id, token = await _admin(dsns, client)
    otro_user = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="otro@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    mia = await seed_invoice(
        dsns, tenant_id=tenant_id, company_id=company_id, confirmed_by=admin_id
    )
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, confirmed_by=otro_user)

    resp = await client.get(
        PANEL_URL, params={"confirmed_by": admin_id}, headers=auth(token, "ilex.localhost")
    )

    assert resp.status_code == 200, resp.text
    assert {i["id"] for i in resp.json()["items"]} == {mia}


async def test_c5_filtro_por_estado_del_cif(authapi: Api) -> None:
    """C5: filtro `cif_status` deja solo las facturas con ese estado del CIF de contraparte."""
    client, dsns = authapi
    tenant_id, admin_id, company_id, token = await _admin(dsns, client)
    unverified = await seed_invoice(
        dsns, tenant_id=tenant_id, company_id=company_id, counterparty_cif_status="unverified"
    )
    await seed_invoice(
        dsns, tenant_id=tenant_id, company_id=company_id, counterparty_cif_status="valid"
    )

    resp = await client.get(
        PANEL_URL, params={"cif_status": "unverified"}, headers=auth(token, "ilex.localhost")
    )

    assert resp.status_code == 200, resp.text
    assert {i["id"] for i in resp.json()["items"]} == {unverified}


async def test_c6_filtro_por_empresa(authapi: Api) -> None:
    """C6: filtro `company_id` acota a una única empresa de la asesoría."""
    client, dsns = authapi
    tenant_id, admin_id, company_1, token = await _admin(dsns, client)
    company_2 = await seed_company(dsns["admin"], tenant_id=tenant_id, name="E2", cif="B06183446")
    de_1 = await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_1)
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_2)

    resp = await client.get(
        PANEL_URL, params={"company_id": company_1}, headers=auth(token, "ilex.localhost")
    )

    assert resp.status_code == 200, resp.text
    assert {i["id"] for i in resp.json()["items"]} == {de_1}


async def test_c7_paginacion_por_cursor(authapi: Api) -> None:
    """C7: la segunda página (con el cursor de la primera) trae el resto sin repetir ni saltar."""
    client, dsns = authapi
    tenant_id, admin_id, company_id, token = await _admin(dsns, client)
    now = datetime.now(UTC)
    ids = []
    for i in range(3):
        inv_id = await seed_invoice(
            dsns,
            tenant_id=tenant_id,
            company_id=company_id,
            confirmed_at=now - timedelta(minutes=i),
        )
        ids.append(inv_id)

    from unittest.mock import patch  # noqa: PLC0415

    import reporting.repository as reporting_repo  # noqa: PLC0415

    with patch.object(reporting_repo, "PAGE_SIZE", 2):
        first = await client.get(PANEL_URL, headers=auth(token, "ilex.localhost"))
        assert first.status_code == 200, first.text
        first_body = first.json()
        assert len(first_body["items"]) == 2
        assert first_body["next_cursor"] is not None

        second = await client.get(
            PANEL_URL,
            params={"cursor": first_body["next_cursor"]},
            headers=auth(token, "ilex.localhost"),
        )
        assert second.status_code == 200, second.text
        second_body = second.json()

    first_ids = {i["id"] for i in first_body["items"]}
    second_ids = {i["id"] for i in second_body["items"]}
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == set(ids)
    assert second_body["next_cursor"] is None


async def test_c8_fila_trae_tramos_iva_irpf_y_fichero(authapi: Api) -> None:
    """C8: cada fila trae importes, tramos de IVA, IRPF, fecha de subida y uploaded_file_id."""
    client, dsns = authapi
    tenant_id, admin_id, company_id, token = await _admin(dsns, client)
    await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        irpf_amount="10.00",
        tax_lines=[{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}],
    )

    resp = await client.get(PANEL_URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    item = resp.json()["items"][0]
    assert item["irpf_amount"] == "10.00"
    assert item["tax_lines"] == [{"iva_pct": "21", "base": "100.00", "cuota": "21.00"}]
    assert "uploaded_at" in item
    assert "uploaded_file_id" in item


async def test_c9_solo_tenant_admin_accede(authapi: Api) -> None:
    """C9: un empleado (`user`) no accede al panel -> 403."""
    client, dsns = authapi
    tenant_id, admin_id, company_id, _admin_token = await _admin(dsns, client)
    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="empleado@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    login_resp = await login(client, "ilex.localhost", "empleado@ilex.es", USER_PASSWORD)
    assert login_resp.status_code == 200, login_resp.text
    empleado_token = login_resp.json()["access_token"]

    resp = await client.get(PANEL_URL, headers=auth(empleado_token, "ilex.localhost"))

    assert resp.status_code == 403, resp.text


async def test_c10_sin_autenticar_no_hay_panel(authapi: Api) -> None:
    """C10: sin token válido -> 401."""
    client, dsns = authapi
    await _admin(dsns, client)

    resp = await client.get(PANEL_URL, headers={"Host": "ilex.localhost"})

    assert resp.status_code == 401, resp.text


async def test_c11_anti_cruce_entre_asesorias(authapi: Api) -> None:
    """C11: el panel de una asesoría nunca trae facturas de otra."""
    client, dsns = authapi
    tenant_id, admin_id, company_id, token = await _admin(dsns, client, slug="ilex")
    tid_otra = await seed_tenant(dsns["admin"], "otra-panel", "Otra Panel")
    comp_otra = await seed_company(dsns["admin"], tenant_id=tid_otra, name="EO", cif="B06183446")
    mia = await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id)
    await seed_invoice(dsns, tenant_id=tid_otra, company_id=comp_otra)

    resp = await client.get(PANEL_URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert {i["id"] for i in resp.json()["items"]} == {mia}


async def test_c12_facturas_de_prueba_excluidas(authapi: Api) -> None:
    """C12: `is_test = true` nunca aparece en el panel."""
    client, dsns = authapi
    tenant_id, admin_id, company_id, token = await _admin(dsns, client)
    normal = await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, is_test=False)
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, is_test=True)

    resp = await client.get(PANEL_URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert {i["id"] for i in resp.json()["items"]} == {normal}


async def test_c2b_rango_de_fechas_invertido_da_422(authapi: Api) -> None:
    """Caso límite (spec §5): date_from posterior a date_to -> 422, no lista vacía silenciosa."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token = await _admin(dsns, client)

    resp = await client.get(
        PANEL_URL,
        params={"date_from": "2026-06-30", "date_to": "2026-06-01"},
        headers=auth(token, "ilex.localhost"),
    )

    assert resp.status_code == 422, resp.text


async def test_c7b_cursor_corrupto_da_422(authapi: Api) -> None:
    """Caso límite (spec §5): un cursor manipulado/corrupto -> 422."""
    client, dsns = authapi
    _tenant_id, _admin_id, _company_id, token = await _admin(dsns, client)

    resp = await client.get(
        PANEL_URL,
        params={"cursor": base64.urlsafe_b64encode(b"basura-sin-formato").decode()},
        headers=auth(token, "ilex.localhost"),
    )

    assert resp.status_code == 422, resp.text


async def test_c6b_empresa_de_otro_tenant_da_lista_vacia(authapi: Api) -> None:
    """Caso límite (spec §5): company_id ajeno -> 200 lista vacía, no error ni fuga de info."""
    client, dsns = authapi
    tenant_id, admin_id, company_id, token = await _admin(dsns, client, slug="ilex")
    tid_otra = await seed_tenant(dsns["admin"], "otra-panel-2", "Otra Panel 2")
    comp_otra = await seed_company(dsns["admin"], tenant_id=tid_otra, name="EO", cif="B06183446")
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id)

    resp = await client.get(
        PANEL_URL, params={"company_id": comp_otra}, headers=auth(token, "ilex.localhost")
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["items"] == []

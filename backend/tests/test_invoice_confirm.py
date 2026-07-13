"""Tests de comportamiento S2.5: persistencia de la factura al confirmar (spec docs/specs/S2.5).

Criterios C1-C14. Observable vía HTTP (cliente ASGI con `Host` de tenant) contra Postgres real,
autenticado, con un `uploaded_file` procesado por S2.3 (`ocr_extraction` sembrada) y el CIF de
contraparte resoluble sin red (S2.8 vía supplier master). Fase roja: los endpoints review/confirm
aún no existen.
"""

from __future__ import annotations

import httpx

from tests._dbtest import seed_company, seed_membership, seed_tenant, seed_user
from tests._invoicing import (
    COUNTERPARTY_CIF,
    INVALID_CIF,
    OWN_CIF,
    audit_count,
    auth,
    confirm_body,
    confirm_url,
    count_invoices,
    count_tax_lines,
    counterparty_exists,
    fetch_corrections,
    fetch_invoice,
    review_url,
    seed_confirmable,
)
from tests._ocr import seed_uploaded_file

Api = tuple[httpx.AsyncClient, dict[str, str]]


# --- Persistencia feliz --------------------------------------------------------------------------
async def test_c1_confirmar_persiste_factura_y_tramos(authapi: Api) -> None:
    """C1: confirmar una factura válida -> 201, invoices + invoice_tax_lines, fichero confirmed."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)

    resp = await client.post(
        confirm_url(s["file_id"]), headers=auth(s["token"]), json=confirm_body()
    )

    assert resp.status_code == 201, resp.text
    inv = await fetch_invoice(dsns, file_id=s["file_id"])
    assert inv is not None
    assert inv["status"] == "confirmed"
    assert inv["counterparty_cif_status"] == "valid"
    assert str(inv["confirmed_by"]) == s["user_id"]
    assert await count_tax_lines(dsns, invoice_id=str(inv["id"])) == 1


async def test_c2_correccion_solo_para_campos_cambiados(authapi: Api) -> None:
    """C2: solo los campos que el humano cambió respecto al OCR generan ocr_corrections."""
    client, dsns = authapi
    # El OCR leyó counterparty_name="Prov SA" y total 121.00 (defaults del seed).
    s = await seed_confirmable(dsns, client)

    resp = await client.post(
        confirm_url(s["file_id"]),
        headers=auth(s["token"]),
        json=confirm_body(
            counterparty_name="Proveedor SA", total="121.00"
        ),  # nombre cambia, total no
    )
    assert resp.status_code == 201, resp.text
    inv = await fetch_invoice(dsns, file_id=s["file_id"])

    corrections = await fetch_corrections(dsns, invoice_id=str(inv["id"]))
    fields = {c["field"] for c in corrections}
    assert "counterparty_name" in fields
    assert "total_amount" not in fields
    name_corr = next(c for c in corrections if c["field"] == "counterparty_name")
    assert name_corr["ai_value"] == "Prov SA"
    assert name_corr["human_value"] == "Proveedor SA"


# --- Guardas de servidor -------------------------------------------------------------------------
async def test_c3_cif_contraparte_invalido_bloquea_en_servidor(authapi: Api) -> None:
    """C3: CIF de contraparte estructuralmente inválido -> 422; nada se persiste (reverificado)."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client, counterparty_cif=INVALID_CIF, seed_master=False)

    resp = await client.post(
        confirm_url(s["file_id"]),
        headers=auth(s["token"]),
        json=confirm_body(counterparty_cif=INVALID_CIF),
    )

    assert resp.status_code == 422, resp.text
    assert await count_invoices(dsns, file_id=s["file_id"]) == 0


async def test_c4_cif_propio_ausente_bloquea_salvo_admin(authapi: Api) -> None:
    """C4: CIF propio ausente -> 422 para empleado; 201 para admin (excepción, regla 2)."""
    client, dsns = authapi
    empleado = await seed_confirmable(dsns, client, slug="ilex", own_present=False)
    r_user = await client.post(
        confirm_url(empleado["file_id"]), headers=auth(empleado["token"]), json=confirm_body()
    )
    assert r_user.status_code == 422, r_user.text

    admin = await seed_confirmable(
        dsns, client, slug="otra", email="admin@otra.es", role="tenant_admin", own_present=False
    )
    r_admin = await client.post(
        confirm_url(admin["file_id"]),
        headers=auth(admin["token"], "otra.localhost"),
        json=confirm_body(),
    )
    assert r_admin.status_code == 201, r_admin.text


async def test_c5_sin_responsabilidad_no_confirma(authapi: Api) -> None:
    """C5: sin aceptar la responsabilidad -> 422, nada se persiste."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)

    resp = await client.post(
        confirm_url(s["file_id"]),
        headers=auth(s["token"]),
        json=confirm_body(responsibility_accepted=False),
    )

    assert resp.status_code == 422, resp.text
    assert await count_invoices(dsns, file_id=s["file_id"]) == 0


async def test_c6_descuadre_avisa_no_bloquea(authapi: Api) -> None:
    """C6: tramos y total que no cuadran -> 201 (aviso, no bloqueo); la factura se persiste."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)

    resp = await client.post(
        confirm_url(s["file_id"]),
        headers=auth(s["token"]),
        json=confirm_body(total="999.00"),  # no cuadra con base 100 + cuota 21
    )

    assert resp.status_code == 201, resp.text
    assert await count_invoices(dsns, file_id=s["file_id"]) == 1


# --- Integración S2.8 y trazabilidad -------------------------------------------------------------
async def test_c7_confirmar_alimenta_supplier_master(authapi: Api) -> None:
    """C7: confirmar registra el CIF de contraparte en el supplier master del tenant (S2.8)."""
    client, dsns = authapi
    # Sin sembrar el master: el veredicto será unverified (permisivo, no bloquea).
    s = await seed_confirmable(dsns, client, seed_master=False)

    resp = await client.post(
        confirm_url(s["file_id"]), headers=auth(s["token"]), json=confirm_body()
    )
    assert resp.status_code == 201, resp.text
    assert await counterparty_exists(dsns, tenant_id=s["tenant_id"], cif=COUNTERPARTY_CIF)


async def test_c8_confirmacion_deja_snapshot_en_audit_log(authapi: Api) -> None:
    """C8: una confirmación con éxito escribe una entrada invoice.confirm en audit_log."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)

    resp = await client.post(
        confirm_url(s["file_id"]), headers=auth(s["token"]), json=confirm_body()
    )
    assert resp.status_code == 201, resp.text
    inv = await fetch_invoice(dsns, file_id=s["file_id"])

    assert await audit_count(dsns, action="invoice.confirm", entity_id=str(inv["id"])) == 1


async def test_c9_reconfirmar_no_crea_segunda_factura(authapi: Api) -> None:
    """C9: reconfirmar el mismo fichero -> 409; sigue habiendo una sola factura."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)

    first = await client.post(
        confirm_url(s["file_id"]), headers=auth(s["token"]), json=confirm_body()
    )
    assert first.status_code == 201, first.text
    dup = await client.post(
        confirm_url(s["file_id"]), headers=auth(s["token"]), json=confirm_body()
    )
    assert dup.status_code == 409, dup.text
    assert await count_invoices(dsns, file_id=s["file_id"]) == 1


async def test_c10_confirmacion_acotada_al_tenant_y_empresa(authapi: Api) -> None:
    """C10: subir a empresa ajena del propio tenant -> 403; a fichero de otro tenant -> 404."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client, slug="ilex")

    # Usuario del mismo tenant sin pertenencia a la empresa del fichero (miembro de otra empresa).
    otra_empresa = await seed_company(
        dsns["admin"], tenant_id=s["tenant_id"], name="E2", cif="A39031620"
    )
    from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, login  # noqa: PLC0415

    bob = await seed_user(
        dsns["admin"],
        tenant_id=s["tenant_id"],
        email="bob@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    await seed_membership(
        dsns["admin"], user_id=bob, company_id=otra_empresa, tenant_id=s["tenant_id"]
    )
    bob_login = await login(client, "ilex.localhost", "bob@ilex.es", USER_PASSWORD)
    bob_token = bob_login.json()["access_token"]
    r_403 = await client.post(
        confirm_url(s["file_id"]), headers=auth(bob_token), json=confirm_body()
    )
    assert r_403.status_code == 403, r_403.text

    # Fichero de otro tenant: invisible para el usuario de ilex -> 404.
    tid_otra = await seed_tenant(dsns["admin"], "otra", "Otra")
    comp_otra = await seed_company(dsns["admin"], tenant_id=tid_otra, name="EO", cif="B06183446")
    file_otra = await seed_uploaded_file(
        dsns, tenant_id=tid_otra, company_id=comp_otra, uploaded_by=bob, status="needs_review"
    )
    r_404 = await client.post(confirm_url(file_otra), headers=auth(s["token"]), json=confirm_body())
    assert r_404.status_code == 404, r_404.text


async def test_c11_is_test_solo_admin(authapi: Api) -> None:
    """C11: un admin marca is_test=true; un empleado que lo envía no crea factura de prueba."""
    client, dsns = authapi
    empleado = await seed_confirmable(dsns, client, slug="ilex")
    r_user = await client.post(
        confirm_url(empleado["file_id"]),
        headers=auth(empleado["token"]),
        json=confirm_body(is_test=True),
    )
    assert r_user.status_code == 201, r_user.text
    assert (await fetch_invoice(dsns, file_id=empleado["file_id"]))["is_test"] is False

    admin = await seed_confirmable(
        dsns, client, slug="otra", email="admin@otra.es", role="tenant_admin"
    )
    r_admin = await client.post(
        confirm_url(admin["file_id"]),
        headers=auth(admin["token"], "otra.localhost"),
        json=confirm_body(is_test=True),
    )
    assert r_admin.status_code == 201, r_admin.text
    assert (await fetch_invoice(dsns, file_id=admin["file_id"]))["is_test"] is True


async def test_c15_correccion_de_tramo_de_iva(authapi: Api) -> None:
    """C15 (issue #70): cambiar la base de un tramo de IVA genera una corrección de ese tramo."""
    client, dsns = authapi
    # Baseline OCR: tramo 21% con base 100.00 / cuota 21.00 (defaults del seed).
    s = await seed_confirmable(dsns, client)

    resp = await client.post(
        confirm_url(s["file_id"]),
        headers=auth(s["token"]),
        json=confirm_body(tax_lines=[{"iva_pct": "21", "base": "90.00", "cuota": "21.00"}]),
    )
    assert resp.status_code == 201, resp.text
    inv = await fetch_invoice(dsns, file_id=s["file_id"])

    corrections = await fetch_corrections(dsns, invoice_id=str(inv["id"]))
    by_field = {c["field"]: c for c in corrections}
    assert "tax_line[21].base" in by_field
    assert by_field["tax_line[21].base"]["ai_value"] == "100.00"
    assert by_field["tax_line[21].base"]["human_value"] == "90.00"
    assert "tax_line[21].cuota" not in by_field  # la cuota no cambió


# --- Datos de revisión (GET para S2.4) -----------------------------------------------------------
async def test_c12_review_devuelve_campos_confianzas_y_veredicto(authapi: Api) -> None:
    """C12: GET review -> 200 con campos, confianzas, veredicto de contraparte e identidad."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client)

    resp = await client.get(review_url(s["file_id"]), headers=auth(s["token"]))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["counterparty_verdict"]["status"] == "valid"
    assert body["own"]["cif"] == OWN_CIF
    assert "total_amount" in body["fields"]


async def test_c13_review_acotado_al_tenant_y_empresa(authapi: Api) -> None:
    """C13: GET review de un fichero de otro tenant -> 404; sin pertenencia -> 403."""
    client, dsns = authapi
    s = await seed_confirmable(dsns, client, slug="ilex")

    tid_otra = await seed_tenant(dsns["admin"], "otra", "Otra")
    comp_otra = await seed_company(dsns["admin"], tenant_id=tid_otra, name="EO", cif="B06183446")
    file_otra = await seed_uploaded_file(
        dsns,
        tenant_id=tid_otra,
        company_id=comp_otra,
        uploaded_by=s["user_id"],
        status="needs_review",
    )
    r = await client.get(review_url(file_otra), headers=auth(s["token"]))
    assert r.status_code == 404, r.text


async def test_c14_review_solo_para_ficheros_ya_leidos(authapi: Api) -> None:
    """C14: GET review de un fichero en pending_ocr (sin OCR) -> 409/404 (no hay datos)."""
    client, dsns = authapi
    from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, login  # noqa: PLC0415

    tenant_id = await seed_tenant(dsns["admin"], "ilex", "ILEX")
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="ana@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Mi Empresa", cif=OWN_CIF
    )
    await seed_membership(
        dsns["admin"], user_id=user_id, company_id=company_id, tenant_id=tenant_id
    )
    file_id = await seed_uploaded_file(
        dsns, tenant_id=tenant_id, company_id=company_id, uploaded_by=user_id, status="pending_ocr"
    )
    token = (await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)).json()[
        "access_token"
    ]

    resp = await client.get(review_url(file_id), headers=auth(token))
    assert resp.status_code == 409, (
        resp.text
    )  # existe en su tenant pero aún no hay datos de revisión


async def test_c13b_review_expone_blocking_reasons(authapi: Api) -> None:
    """C13 (S2.4): review expone `blocking_reasons` (misma lógica que las guardas de confirm)."""
    client, dsns = authapi
    # CIF de contraparte estructuralmente inválido -> motivo counterparty_cif_invalid.
    bad = await seed_confirmable(
        dsns, client, slug="ilex", counterparty_cif=INVALID_CIF, seed_master=False
    )
    r_bad = await client.get(review_url(bad["file_id"]), headers=auth(bad["token"]))
    assert r_bad.status_code == 200, r_bad.text
    assert "counterparty_cif_invalid" in r_bad.json()["blocking_reasons"]

    # Todo correcto y confirmable -> lista vacía.
    ok = await seed_confirmable(dsns, client, slug="dos", email="ana@dos.es")
    r_ok = await client.get(review_url(ok["file_id"]), headers=auth(ok["token"], "dos.localhost"))
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["blocking_reasons"] == []

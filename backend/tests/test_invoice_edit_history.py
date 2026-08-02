"""Tests de comportamiento: historial de EDICIONES de una factura (2026-08-01, decisión de Julio).

No confundir con `test_invoice_history.py` (S2.6, historial de subidas de los últimos 7 días, otro
concepto y otro endpoint). `invoice_edits` existía desde S3.3 pero era solo escritura: `GET
/invoices/{id}/history` la expone por primera vez. Observable vía HTTP (cliente ASGI con `Host` de
tenant), autenticado como `tenant_admin`, contra Postgres real. Mismo patrón que
`test_invoice_edit.py`.
"""

from __future__ import annotations

import httpx

from tests._counterparty import seed_counterparty
from tests._dbtest import seed_company, seed_tenant
from tests._invoicing import COUNTERPARTY_CIF, OWN_CIF, auth, seed_invoice
from tests._reporting import seed_admin_with_company

Api = tuple[httpx.AsyncClient, dict[str, str]]


def _history_url(invoice_id: str) -> str:
    return f"/api/v1/invoices/{invoice_id}/history"


def _edit_url(invoice_id: str) -> str:
    return f"/api/v1/invoices/{invoice_id}"


async def _seed_confirmed_invoice(dsns, client, **kwargs):
    tenant_id, admin_id, company_id, token = await seed_admin_with_company(dsns, client)
    invoice_id = await seed_invoice(
        dsns, tenant_id=tenant_id, company_id=company_id, confirmed_by=admin_id, **kwargs
    )
    return tenant_id, admin_id, company_id, token, invoice_id


async def test_c1_editar_y_consultar_devuelve_el_valor_anterior_y_el_nuevo(authapi: Api) -> None:
    """C1: tras editar `total_amount`, el historial trae esa fila con antes/después."""
    client, dsns = authapi
    _tid, _aid, _cid, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, total_amount="121.00"
    )

    edit = await client.patch(
        _edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={"total_amount": "150.00"},
    )
    assert edit.status_code == 200, edit.text

    resp = await client.get(_history_url(invoice_id), headers=auth(token, "ilex.localhost"))
    assert resp.status_code == 200, resp.text
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["field"] == "total_amount"
    assert entries[0]["old_value"] == "121.00"
    assert entries[0]["new_value"] == "150.00"
    assert entries[0]["edited_by"] is not None
    assert entries[0]["edited_at"] is not None


async def test_c2_sin_ediciones_el_historial_esta_vacio(authapi: Api) -> None:
    """C2: una factura recién confirmada, nunca editada -> historial vacío, no un error."""
    client, dsns = authapi
    _tid, _aid, _cid, token, invoice_id = await _seed_confirmed_invoice(dsns, client)

    resp = await client.get(_history_url(invoice_id), headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_c3_historial_de_otro_tenant_da_404(authapi: Api) -> None:
    """C3: pedir el historial de una factura de OTRO tenant -> 404, igual que editarla."""
    client, dsns = authapi
    _tid, _aid, _cid, token, _own_invoice_id = await _seed_confirmed_invoice(dsns, client)

    other_tenant = await seed_tenant(dsns["admin"], "otra", "Otra SL")
    other_company = await seed_company(
        dsns["admin"], tenant_id=other_tenant, name="Ajena SL", cif=OWN_CIF
    )
    other_invoice_id = await seed_invoice(dsns, tenant_id=other_tenant, company_id=other_company)

    resp = await client.get(_history_url(other_invoice_id), headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 404, resp.text


async def test_c4_campos_sensibles_del_historial_llegan_descifrados_por_la_api(
    authapi: Api,
) -> None:
    """C4: `counterparty_tax_id`/`counterparty_name` (cifrados en `invoice_edits`, S5.2 C7) llegan
    en claro a través de la API — el cifrado protege la fila cruda, no al usuario legítimo."""
    client, dsns = authapi
    tenant_id, _aid, _cid, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, counterparty_tax_id=COUNTERPARTY_CIF, counterparty_name="Proveedor SA"
    )
    await seed_counterparty(dsns, tenant_id=tenant_id, cif=OWN_CIF, name="Otro Proveedor SA")

    edit = await client.patch(
        _edit_url(invoice_id),
        headers=auth(token, "ilex.localhost"),
        json={"counterparty_tax_id": OWN_CIF, "counterparty_name": "Otro Proveedor SA"},
    )
    assert edit.status_code == 200, edit.text

    resp = await client.get(_history_url(invoice_id), headers=auth(token, "ilex.localhost"))
    by_field = {e["field"]: e for e in resp.json()}
    assert by_field["counterparty_tax_id"]["old_value"] == COUNTERPARTY_CIF
    assert by_field["counterparty_tax_id"]["new_value"] == OWN_CIF
    assert by_field["counterparty_name"]["old_value"] == "Proveedor SA"
    assert by_field["counterparty_name"]["new_value"] == "Otro Proveedor SA"


async def test_c5_revertir_es_un_nuevo_patch_con_el_valor_anterior(authapi: Api) -> None:
    """C5: "volver atrás" es un PATCH normal con el valor de una entrada anterior; esa reversión
    queda registrada como una edición más (append-only, retención permanente)."""
    client, dsns = authapi
    _tid, _aid, _cid, token, invoice_id = await _seed_confirmed_invoice(
        dsns, client, total_amount="121.00"
    )
    headers = auth(token, "ilex.localhost")

    await client.patch(_edit_url(invoice_id), headers=headers, json={"total_amount": "150.00"})
    history_before = (await client.get(_history_url(invoice_id), headers=headers)).json()
    old_value = next(e for e in history_before if e["field"] == "total_amount")["old_value"]
    assert old_value == "121.00"

    revert = await client.patch(
        _edit_url(invoice_id), headers=headers, json={"total_amount": old_value}
    )
    assert revert.status_code == 200, revert.text

    history_after = (await client.get(_history_url(invoice_id), headers=headers)).json()
    total_entries = [e for e in history_after if e["field"] == "total_amount"]
    assert len(total_entries) == 2
    assert any(e["old_value"] == "150.00" and e["new_value"] == "121.00" for e in total_entries)

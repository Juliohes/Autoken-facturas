"""Tests de comportamiento: historial de ediciones de una empresa (2026-08-01, decisión de Julio:
cada celda editable, con historial permanente y posibilidad de revertir).

Observable vía HTTP (cliente ASGI con `Host` de tenant) contra Postgres real, autenticado como
`tenant_admin`. Mismo patrón que `test_invoice_edit.py::test_s5_2_c7_...` para verificar el cifrado
de los campos sensibles del rastro.
"""

from __future__ import annotations

import asyncpg
import httpx

from tests._companies import COMPANIES, VALID_CIF, VALID_CIF_2, admin_token, seed_admin
from tests._dbtest import seed_company, seed_tenant

Api = tuple[httpx.AsyncClient, dict[str, str]]


def _history_url(company_id: str) -> str:
    return f"{COMPANIES}/{company_id}/history"


async def test_c1_editar_varios_campos_deja_una_fila_por_campo(authapi: Api) -> None:
    """C1: editar nombre/CIF/notas/estado a la vez deja 4 filas en el historial, una por campo."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    cid = await seed_company(
        dsns["admin"], tenant_id=tid, name="Original SL", cif=VALID_CIF, status="pending"
    )
    token = await admin_token(client)

    resp = await client.patch(
        f"{COMPANIES}/{cid}",
        json={
            "name": "Nueva SL",
            "cif": VALID_CIF_2,
            "notes": "revisada",
            "status": "active",
        },
        headers={"Host": "ilex.localhost", "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text

    history = await client.get(
        _history_url(cid), headers={"Host": "ilex.localhost", "Authorization": f"Bearer {token}"}
    )
    assert history.status_code == 200, history.text
    by_field = {e["field"]: e for e in history.json()}
    assert set(by_field) == {"name", "cif", "notes", "status"}
    assert by_field["name"]["old_value"] == "Original SL"
    assert by_field["name"]["new_value"] == "Nueva SL"
    assert by_field["cif"]["old_value"] == VALID_CIF
    assert by_field["cif"]["new_value"] == VALID_CIF_2
    assert by_field["notes"]["old_value"] is None
    assert by_field["notes"]["new_value"] == "revisada"
    assert by_field["status"]["old_value"] == "pending"
    assert by_field["status"]["new_value"] == "active"
    assert all(e["edited_by"] is not None and e["edited_at"] is not None for e in by_field.values())


async def test_c2_reenviar_los_mismos_valores_no_deja_rastro_nuevo(authapi: Api) -> None:
    """C2: un PATCH sin cambios reales (mismo valor reenviado) no añade filas al historial."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    cid = await seed_company(dsns["admin"], tenant_id=tid, name="Igual SL", cif=VALID_CIF)
    token = await admin_token(client)
    headers = {"Host": "ilex.localhost", "Authorization": f"Bearer {token}"}

    resp = await client.patch(f"{COMPANIES}/{cid}", json={"name": "Igual SL"}, headers=headers)
    assert resp.status_code == 200, resp.text

    history = await client.get(_history_url(cid), headers=headers)
    assert history.json() == []


async def test_c3_campos_sensibles_del_historial_van_cifrados(authapi: Api) -> None:
    """C3: `name`/`cif` en `company_edits.old_value`/`new_value` nunca en texto plano en la fila
    cruda (mismo motivo que S5.2 C7 para `invoice_edits`: dejarlos en claro en la auditoría sería
    una fuga paralela del mismo dato que se acaba de proteger)."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    cid = await seed_company(dsns["admin"], tenant_id=tid, name="Secreta SL", cif=VALID_CIF)
    token = await admin_token(client)
    headers = {"Host": "ilex.localhost", "Authorization": f"Bearer {token}"}

    resp = await client.patch(
        f"{COMPANIES}/{cid}",
        json={"name": "Renombrada SL", "cif": VALID_CIF_2, "notes": "nota en claro"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    conn = await asyncpg.connect(dsns["admin"])
    try:
        rows = await conn.fetch(
            "SELECT field, old_value, new_value FROM company_edits WHERE company_id = $1", cid
        )
    finally:
        await conn.close()
    by_field = {r["field"]: r for r in rows}
    assert "Secreta SL" not in by_field["name"]["old_value"]
    assert "Renombrada SL" not in by_field["name"]["new_value"]
    assert VALID_CIF not in by_field["cif"]["old_value"]
    assert VALID_CIF_2 not in by_field["cif"]["new_value"]
    # `notes` no es sensible: sigue en claro en la fila cruda, como siempre.
    assert by_field["notes"]["new_value"] == "nota en claro"

    # El camino que descifra (la propia API) sí recupera los valores originales.
    history = await client.get(_history_url(cid), headers=headers)
    decrypted = {e["field"]: e for e in history.json()}
    assert decrypted["name"]["old_value"] == "Secreta SL"
    assert decrypted["name"]["new_value"] == "Renombrada SL"
    assert decrypted["cif"]["old_value"] == VALID_CIF
    assert decrypted["cif"]["new_value"] == VALID_CIF_2


async def test_c4_historial_de_otro_tenant_da_404(authapi: Api) -> None:
    """C4: pedir el historial de una empresa de OTRO tenant -> 404, igual que editarla (anti-cruce
    de tenants)."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    token = await admin_token(client)

    other_tenant = await seed_tenant(dsns["admin"], "otra", "Otra SL")
    other_company = await seed_company(
        dsns["admin"], tenant_id=other_tenant, name="Ajena SL", cif=VALID_CIF_2
    )

    resp = await client.get(
        _history_url(other_company),
        headers={"Host": "ilex.localhost", "Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404, resp.text


async def test_c5_revertir_es_un_nuevo_patch_con_el_valor_anterior(authapi: Api) -> None:
    """C5: "volver atrás" no es un endpoint especial — es un PATCH normal con el valor de una
    entrada anterior del historial, que a su vez queda registrado como una edición más
    (append-only, nunca se borra ni se sobreescribe el historial, retención permanente)."""
    client, dsns = authapi
    tid, _ = await seed_admin(dsns)
    cid = await seed_company(dsns["admin"], tenant_id=tid, name="Version 1", cif=VALID_CIF)
    token = await admin_token(client)
    headers = {"Host": "ilex.localhost", "Authorization": f"Bearer {token}"}

    await client.patch(f"{COMPANIES}/{cid}", json={"name": "Version 2"}, headers=headers)

    history_before = (await client.get(_history_url(cid), headers=headers)).json()
    old_value = next(e for e in history_before if e["field"] == "name")["old_value"]
    assert old_value == "Version 1"

    revert = await client.patch(f"{COMPANIES}/{cid}", json={"name": old_value}, headers=headers)
    assert revert.status_code == 200, revert.text
    assert revert.json()["name"] == "Version 1"

    history_after = (await client.get(_history_url(cid), headers=headers)).json()
    name_entries = [e for e in history_after if e["field"] == "name"]
    assert len(name_entries) == 2  # la edición original + la de revertir, ninguna se pierde
    assert any(
        e["old_value"] == "Version 2" and e["new_value"] == "Version 1" for e in name_entries
    )

"""Tests de comportamiento S3.4: ficha agregada de empresas (spec docs/specs/S3.4).

Criterios C1-C8 (backend). Observable vía HTTP (cliente ASGI con `Host` de tenant), autenticado
como `tenant_admin`, contra Postgres real. Fase roja: el endpoint `GET /reporting/companies` aún
no existe.
"""

from __future__ import annotations

import httpx

from tests._dbtest import seed_company, seed_membership, seed_tenant, seed_user
from tests._intake import seed_tenant_admin, token_for
from tests._invoicing import auth, seed_invoice

Api = tuple[httpx.AsyncClient, dict[str, str]]

URL = "/api/v1/reporting/companies"


async def test_c1_listar_devuelve_la_ficha_completa(authapi: Api) -> None:
    """C1: la fila trae id, name, cif, status, notes, created_at y los tres contadores."""
    client, dsns = authapi
    tenant_id, _admin_id = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    await seed_company(
        dsns["admin"],
        tenant_id=tenant_id,
        name="Empresa Uno",
        cif="A39031620",
        notes="cliente desde 2020",
    )
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.get(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["name"] == "Empresa Uno"
    assert row["cif"] == "A39031620"
    assert row["status"] == "active"
    assert row["notes"] == "cliente desde 2020"
    assert row["created_at"] is not None
    assert row["user_count"] == 0
    assert row["invoice_count"] == 0
    assert row["last_invoice_at"] is None


async def test_c2_user_count_solo_cuenta_usuarios_activos(authapi: Api) -> None:
    """C2: dos usuarios `active` y uno `pending` en la misma empresa -> user_count = 2."""
    client, dsns = authapi
    tenant_id, _admin_id = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Empresa Uno", cif="A39031620"
    )
    for i in range(2):
        uid = await seed_user(
            dsns["admin"], tenant_id=tenant_id, email=f"activo{i}@ilex.es", status="active"
        )
        await seed_membership(
            dsns["admin"], user_id=uid, company_id=company_id, tenant_id=tenant_id
        )
    pending_id = await seed_user(
        dsns["admin"], tenant_id=tenant_id, email="pendiente@ilex.es", status="pending"
    )
    await seed_membership(
        dsns["admin"], user_id=pending_id, company_id=company_id, tenant_id=tenant_id
    )
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.get(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    row = resp.json()[0]
    assert row["user_count"] == 2


async def test_c3_invoice_count_excluye_facturas_de_prueba(authapi: Api) -> None:
    """C3: 3 facturas reales + 1 de prueba -> invoice_count=3; last_invoice_at es la real más
    reciente."""
    client, dsns = authapi
    tenant_id, _admin_id = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Empresa Uno", cif="A39031620"
    )
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, days_ago=2)
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, days_ago=1)
    await seed_invoice(dsns, tenant_id=tenant_id, company_id=company_id, days_ago=0)
    await seed_invoice(
        dsns, tenant_id=tenant_id, company_id=company_id, days_ago=-10, is_test=True
    )
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.get(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    row = resp.json()[0]
    assert row["invoice_count"] == 3
    assert row["last_invoice_at"] is not None


async def test_c4_empresa_sin_facturas(authapi: Api) -> None:
    """C4: empresa recién creada sin facturas -> invoice_count=0, last_invoice_at=null."""
    client, dsns = authapi
    tenant_id, _admin_id = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    await seed_company(dsns["admin"], tenant_id=tenant_id, name="Empresa Nueva", cif="A39031620")
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.get(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    row = resp.json()[0]
    assert row["invoice_count"] == 0
    assert row["last_invoice_at"] is None


async def test_c4b_notas_ausentes_se_devuelven_como_null_no_cadena_vacia(authapi: Api) -> None:
    """C4b (spec §5): una empresa sin notas devuelve `notes: null`, no `""`."""
    client, dsns = authapi
    tenant_id, _admin_id = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    await seed_company(dsns["admin"], tenant_id=tenant_id, name="Sin Notas", cif="A39031620")
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.get(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["notes"] is None


async def test_c5_orden_por_nombre(authapi: Api) -> None:
    """C5: el listado va alfabético por nombre, no por orden de alta."""
    client, dsns = authapi
    tenant_id, _admin_id = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    await seed_company(dsns["admin"], tenant_id=tenant_id, name="Zeta", cif="A39031620")
    await seed_company(dsns["admin"], tenant_id=tenant_id, name="Alfa", cif="B06183446")
    await seed_company(dsns["admin"], tenant_id=tenant_id, name="Beta", cif="A58818501")
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.get(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    names = [row["name"] for row in resp.json()]
    assert names == ["Alfa", "Beta", "Zeta"]


async def test_c6_un_empleado_no_puede_listar(authapi: Api) -> None:
    """C6: `user` (no `tenant_admin`) -> 403."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    from tests._auth import USER_PASSWORD_HASH  # noqa: PLC0415

    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="empleado@ilex.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
    )
    token = await token_for(client, email="empleado@ilex.es", hostname="ilex.localhost")

    resp = await client.get(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 403


async def test_c7_sin_autenticar_no_hay_listado(authapi: Api) -> None:
    """C7: sin token válido -> 401."""
    client, _dsns = authapi

    resp = await client.get(URL, headers=auth("token-invalido", "ilex.localhost"))

    assert resp.status_code == 401


async def test_c8_anticruce_no_aparecen_empresas_de_otro_tenant(authapi: Api) -> None:
    """C8: `tenant_admin` de `ilex` no ve ninguna empresa de `otra` (RLS)."""
    client, dsns = authapi
    tenant_ilex, _ = await seed_tenant_admin(dsns, slug="ilex", email="admin@ilex.es")
    tenant_otra = await seed_tenant(dsns["admin"], "otra", "Otra Asesoría")
    await seed_company(dsns["admin"], tenant_id=tenant_ilex, name="De Ilex", cif="A39031620")
    await seed_company(dsns["admin"], tenant_id=tenant_otra, name="De Otra", cif="B06183446")
    token = await token_for(client, email="admin@ilex.es", hostname="ilex.localhost")

    resp = await client.get(URL, headers=auth(token, "ilex.localhost"))

    assert resp.status_code == 200, resp.text
    names = {row["name"] for row in resp.json()}
    assert names == {"De Ilex"}

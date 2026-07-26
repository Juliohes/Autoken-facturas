"""Test de comportamiento de la rotación de la clave maestra de cifrado (S5.2 C9, ADR-0018).

`jobs.key_rotation.rotate_all_tenants` re-cifra todo lo cifrado con la clave vieja usando una clave
nueva, tenant a tenant. Contra Postgres real (fixture `authapi`), con dos tenants para comprobar que
la rotación no cruza sus datos entre sí (misma disciplina anti-cruce que el resto del proyecto).
"""

from __future__ import annotations

from uuid import UUID

import httpx
import pytest

from tests._dbtest import seed_company, seed_tenant, seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]

_NEW_MASTER_KEY = "clave-maestra-nueva-de-prueba-tras-la-rotacion-32b"  # gitleaks:allow (test)


async def test_c9_rotacion_recifra_con_la_clave_nueva_y_la_vieja_deja_de_servir(
    authapi: Api,
) -> None:
    from shared import config
    from shared.encryption import derive_tenant_encryption_key

    _client, dsns = authapi
    old_master_key = config.get_settings().db_encryption_master_key

    tenant_id = await seed_tenant(dsns["admin"], "rota", "Rota Asesoria")
    company_id = await seed_company(
        dsns["admin"], tenant_id=tenant_id, name="Empresa Rotable SL", cif="A39031620"
    )
    await seed_user(dsns["admin"], tenant_id=tenant_id, email="admin@rota.es")

    from jobs.key_rotation import rotate_all_tenants

    summary = await rotate_all_tenants(old_master=old_master_key, new_master=_NEW_MASTER_KEY)
    assert summary.rotated >= 1

    # La clave VIEJA ya no descifra nada: una tentativa con ella debe fallar (no coincide).
    import asyncpg

    conn = await asyncpg.connect(dsns["admin"])
    try:
        old_key = derive_tenant_encryption_key(old_master_key, tenant_id)
        row = await conn.fetchrow("SELECT cif FROM companies WHERE id = $1", company_id)
        with pytest.raises(asyncpg.PostgresError):
            await conn.fetchval("SELECT pgp_sym_decrypt($1::bytea, $2)::text", row["cif"], old_key)

        new_key = derive_tenant_encryption_key(_NEW_MASTER_KEY, tenant_id)
        decrypted = await conn.fetchval(
            "SELECT pgp_sym_decrypt($1::bytea, $2)::text", row["cif"], new_key
        )
        assert decrypted == "A39031620"
    finally:
        await conn.close()

    # Reanudable: relanzarla detecta que este tenant ya está rotado y lo salta (no falla, no
    # duplica trabajo).
    second_run = await rotate_all_tenants(old_master=old_master_key, new_master=_NEW_MASTER_KEY)
    assert second_run.already_done >= 1


async def test_c9_rotacion_recifra_invoice_edits_de_campos_sensibles(authapi: Api) -> None:
    """S5.2 C7+C9: la rotación también re-cifra `invoice_edits.old_value`/`new_value` de un campo
    sensible (CIF de contraparte), no solo `companies`/`counterparties`/`invoices`.

    Regresión real encontrada durante esta tarea: `invoice_edits` es append-only (solo `SELECT,
    INSERT` concedidos) — la rotación necesitó un `GRANT UPDATE` acotado a esas dos columnas
    (migración 0021) y no puede usar `SELECT ... FOR UPDATE` ahí (exige la fila completa). Sin este
    test, un fallo de permisos en `_rotate_invoice_edits` pasaría desapercibido siempre que ningún
    otro test sembrara una edición sensible antes de rotar.
    """
    import asyncpg

    from shared import config
    from shared.encryption import derive_tenant_encryption_key
    from tests._counterparty import seed_counterparty
    from tests._invoicing import COUNTERPARTY_CIF, OWN_CIF, auth, seed_invoice
    from tests._reporting import seed_admin_with_company

    client, dsns = authapi
    old_master_key = config.get_settings().db_encryption_master_key

    tenant_id, admin_id, company_id, token = await seed_admin_with_company(
        dsns, client, slug="rota"
    )
    invoice_id = await seed_invoice(
        dsns,
        tenant_id=tenant_id,
        company_id=company_id,
        confirmed_by=admin_id,
        counterparty_tax_id=COUNTERPARTY_CIF,
        counterparty_name="Proveedor SA",
    )
    await seed_counterparty(dsns, tenant_id=tenant_id, cif=OWN_CIF, name="Otro Proveedor SA")

    resp = await client.patch(
        f"/api/v1/invoices/{invoice_id}",
        headers=auth(token, "rota.localhost"),
        json={"counterparty_tax_id": OWN_CIF, "counterparty_name": "Otro Proveedor SA"},
    )
    assert resp.status_code == 200, resp.text

    from jobs.key_rotation import rotate_all_tenants

    summary = await rotate_all_tenants(old_master=old_master_key, new_master=_NEW_MASTER_KEY)
    assert summary.rotated >= 1

    conn = await asyncpg.connect(dsns["admin"])
    try:
        rows = await conn.fetch(
            "SELECT field, old_value, new_value FROM invoice_edits WHERE invoice_id = $1",
            invoice_id,
        )
        by_field = {r["field"]: r for r in rows}
        new_key = derive_tenant_encryption_key(_NEW_MASTER_KEY, tenant_id)
        old_key = derive_tenant_encryption_key(old_master_key, tenant_id)

        decrypted_old_cif = await conn.fetchval(
            "SELECT pgp_sym_decrypt(decode($1, 'base64'), $2)::text",
            by_field["counterparty_tax_id"]["old_value"],
            new_key,
        )
        decrypted_new_cif = await conn.fetchval(
            "SELECT pgp_sym_decrypt(decode($1, 'base64'), $2)::text",
            by_field["counterparty_tax_id"]["new_value"],
            new_key,
        )
        assert decrypted_old_cif == COUNTERPARTY_CIF
        assert decrypted_new_cif == OWN_CIF

        with pytest.raises(asyncpg.PostgresError):
            await conn.fetchval(
                "SELECT pgp_sym_decrypt(decode($1, 'base64'), $2)::text",
                by_field["counterparty_tax_id"]["old_value"],
                old_key,
            )
    finally:
        await conn.close()


async def test_c9_rotacion_no_cruza_datos_entre_tenants(authapi: Api) -> None:
    from shared import config
    from shared.encryption import derive_tenant_encryption_key

    _client, dsns = authapi
    old_master_key = config.get_settings().db_encryption_master_key

    tenant_a = await seed_tenant(dsns["admin"], "rota-a", "Rota A")
    tenant_b = await seed_tenant(dsns["admin"], "rota-b", "Rota B")
    company_a = await seed_company(
        dsns["admin"], tenant_id=tenant_a, name="Empresa A", cif="A39031620"
    )
    company_b = await seed_company(
        dsns["admin"], tenant_id=tenant_b, name="Empresa B", cif="B06183446"
    )

    from jobs.key_rotation import rotate_all_tenants

    await rotate_all_tenants(old_master=old_master_key, new_master=_NEW_MASTER_KEY)

    import asyncpg

    conn = await asyncpg.connect(dsns["admin"])
    try:
        row_a = await conn.fetchrow("SELECT cif FROM companies WHERE id = $1", company_a)
        row_b = await conn.fetchrow("SELECT cif FROM companies WHERE id = $1", company_b)
        key_a = derive_tenant_encryption_key(_NEW_MASTER_KEY, tenant_a)
        key_b = derive_tenant_encryption_key(_NEW_MASTER_KEY, tenant_b)

        # La clave del tenant A no descifra los datos del tenant B (claves distintas por tenant).
        with pytest.raises(asyncpg.PostgresError):
            await conn.fetchval("SELECT pgp_sym_decrypt($1::bytea, $2)::text", row_b["cif"], key_a)

        assert (
            await conn.fetchval("SELECT pgp_sym_decrypt($1::bytea, $2)::text", row_a["cif"], key_a)
            == "A39031620"
        )
        assert (
            await conn.fetchval("SELECT pgp_sym_decrypt($1::bytea, $2)::text", row_b["cif"], key_b)
            == "B06183446"
        )
    finally:
        await conn.close()
    assert UUID(tenant_a) != UUID(tenant_b)

"""Pruebas de comportamiento R-027: supervisión global admin-tech."""

from __future__ import annotations

import asyncpg
import httpx

from tests._invoicing import seed_confirmable
from tests._platform import platform_token, seed_platform_admin

Api = tuple[httpx.AsyncClient, dict[str, str]]


def _platform_headers(token: str) -> dict[str, str]:
    return {"Host": "panel.localhost", "Authorization": f"Bearer {token}"}


async def test_r027_sin_flag_no_puede_listar_global(authapi: Api) -> None:
    client, dsns = authapi
    await seed_platform_admin(dsns, is_admin_tech=False)
    token = await platform_token(client)

    response = await client.get("/api/v1/platform/pending", headers=_platform_headers(token))

    assert response.status_code == 403, response.text


async def test_r027_lista_metadata_y_no_abre_documentos_automaticamente(authapi: Api) -> None:
    client, dsns = authapi
    seeded = await seed_confirmable(dsns, client, slug="global-one")
    await seed_platform_admin(dsns, is_admin_tech=True)
    token = await platform_token(client)

    response = await client.get("/api/v1/platform/pending", headers=_platform_headers(token))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["next_cursor"] is None
    item = next(item for item in body["items"] if item["id"] == seeded["file_id"])
    assert item["tenant_id"] == seeded["tenant_id"]
    assert item["company_name"] == "Mi Empresa"
    assert "fields" not in item
    assert "raw" not in item


async def test_r027_apertura_explicita_audita_sin_raw(authapi: Api) -> None:
    client, dsns = authapi
    seeded = await seed_confirmable(dsns, client, slug="global-audit")
    actor_id = await seed_platform_admin(dsns, is_admin_tech=True)
    token = await platform_token(client)

    response = await client.get(
        f"/api/v1/platform/pending/{seeded['tenant_id']}/{seeded['file_id']}/review-readonly",
        headers=_platform_headers(token),
    )

    assert response.status_code == 200, response.text
    assert "fields" in response.json()
    conn = await asyncpg.connect(dsns["admin"])
    try:
        audit = await conn.fetchrow(
            "SELECT actor_id, tenant_id, entity_id, action, request_id, source_ip, payload_hash "
            "FROM audit_log WHERE action = 'admin_tech.pending_document.read' "
            "AND entity_id = $1",
            seeded["file_id"],
        )
    finally:
        await conn.close()

    assert audit is not None
    assert str(audit["actor_id"]) == actor_id
    assert str(audit["tenant_id"]) == seeded["tenant_id"]
    assert str(audit["entity_id"]) == seeded["file_id"]
    assert audit["request_id"]
    assert audit["source_ip"]
    assert audit["payload_hash"]


async def test_r027_no_puede_abrir_un_fichero_de_otro_tenant(authapi: Api) -> None:
    client, dsns = authapi
    first = await seed_confirmable(dsns, client, slug="global-first")
    second = await seed_confirmable(dsns, client, slug="global-second")
    await seed_platform_admin(dsns, is_admin_tech=True)
    token = await platform_token(client)

    response = await client.get(
        f"/api/v1/platform/pending/{first['tenant_id']}/{second['file_id']}/review-readonly",
        headers=_platform_headers(token),
    )

    assert response.status_code == 404, response.text

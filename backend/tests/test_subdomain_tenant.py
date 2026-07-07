"""Tests de comportamiento de S1.2: resolución subdominio -> tenant (spec docs/specs/S1.2).

Observable vía HTTP (cliente ASGI con cabecera `Host`) contra un Postgres real con el esquema de
S1.1 y `resolve_tenant`. La app se conecta como el rol runtime; los tenants se siembran como
superusuario. Cada test = un escenario C1..C7 de la spec.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import asyncpg
import httpx
import pytest

from tests._dbtest import provision_test_db, seed_tenant

_HEALTH = "/api/v1/health"
_CURRENT = "/api/v1/tenants/current"


@pytest.fixture
async def api() -> AsyncIterator[tuple[httpx.AsyncClient, dict[str, str]]]:
    """App wired a la BD de test como rol runtime + cliente HTTP; devuelve (client, dsns)."""
    from shared import config
    from shared import db as db_module

    dsns = await provision_test_db()
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = dsns["app_async"]
    config.get_settings.cache_clear()
    await db_module.dispose_engine()

    from main import create_app

    transport = httpx.ASGITransport(app=create_app())
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, dsns
    finally:
        await db_module.dispose_engine()
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        config.get_settings.cache_clear()


def _host(host: str) -> dict[str, str]:
    return {"Host": host}


async def test_c1_subdominio_de_tenant_activo_resuelve(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """C1: `ilex.autoken.es` resuelve al tenant I-Lex (200 con sus datos públicos)."""
    client, dsns = api
    await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    resp = await client.get(_CURRENT, headers=_host("ilex.autoken.es"))
    assert resp.status_code == 200
    assert resp.json()["slug"] == "ilex"
    assert resp.json()["name"] == "I-Lex Asesoría"


async def test_c2_subdominio_inexistente_da_404_neutro(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """C2: un subdominio sin tenant da 404 genérico."""
    client, _ = api
    resp = await client.get(_CURRENT, headers=_host("nope.autoken.es"))
    assert resp.status_code == 404


async def test_c3_tenant_suspendido_da_404_identico_al_inexistente(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """C3: un tenant suspendido da 404 idéntico al de un subdominio inexistente (no enumera)."""
    client, dsns = api
    await seed_tenant(dsns["admin"], "viejo", "Vieja SL", status="suspended")
    suspendido = await client.get(_CURRENT, headers=_host("viejo.autoken.es"))
    inexistente = await client.get(_CURRENT, headers=_host("nope.autoken.es"))
    assert suspendido.status_code == inexistente.status_code == 404
    assert suspendido.text == inexistente.text  # indistinguibles desde fuera


async def test_c4_hosts_no_tenant_no_fuerzan_404(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """C4: dominio raíz / plataforma no resuelven tenant, pero health sigue respondiendo 200."""
    client, _ = api
    for host in ("autoken.es", "www.autoken.es", "panel.autoken.es"):
        assert (await client.get(_HEALTH, headers=_host(host))).status_code == 200
        assert (await client.get(_CURRENT, headers=_host(host))).status_code == 404


async def test_c5_el_puerto_del_host_se_ignora(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """C5: `ilex.localhost:8000` resuelve igual que sin puerto."""
    client, dsns = api
    await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    resp = await client.get(_CURRENT, headers=_host("ilex.localhost:8000"))
    assert resp.status_code == 200
    assert resp.json()["slug"] == "ilex"


async def test_c6_resolve_tenant_es_el_unico_camino(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """C6: `resolve_tenant` devuelve el tenant, pero el SELECT directo sigue tapado por la RLS."""
    _, dsns = api
    await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    conn = await asyncpg.connect(dsns["app"])  # rol runtime, sin app.tenant_id
    try:
        via_funcion = await conn.fetch("SELECT * FROM resolve_tenant('ilex')")
        via_directo = await conn.fetch("SELECT * FROM tenants WHERE slug = 'ilex'")
    finally:
        await conn.close()
    assert len(via_funcion) == 1
    assert via_funcion[0]["slug"] == "ilex"
    assert len(via_directo) == 0  # la RLS de S1.1 sigue intacta


async def test_c7_resolve_tenant_solo_devuelve_activos(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """C7: `resolve_tenant` no devuelve un tenant suspendido."""
    _, dsns = api
    await seed_tenant(dsns["admin"], "viejo", "Vieja SL", status="suspended")
    conn = await asyncpg.connect(dsns["app"])
    try:
        filas = await conn.fetch("SELECT * FROM resolve_tenant('viejo')")
    finally:
        await conn.close()
    assert len(filas) == 0

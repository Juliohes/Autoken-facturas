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

from tests._auth import bearer
from tests._dbtest import provision_test_db, seed_branding, seed_tenant
from tests._platform import platform_token, seed_platform_admin

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

    # raise_app_exceptions=False: una excepción no controlada se convierte en 500 (como en prod),
    # en vez de propagarse al test (permite comprobar "fallo de BD -> 500").
    transport = httpx.ASGITransport(app=create_app(), raise_app_exceptions=False)
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


# --- S4.2: branding en /tenants/current ----------------------------------------------------------


async def test_s42_c1_devuelve_el_branding_completo_cuando_existe(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """S4.2 C1: con branding puesto, el endpoint lo devuelve tal cual."""
    client, dsns = api
    tenant_id = await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    await seed_branding(
        dsns["admin"],
        tenant_id=tenant_id,
        logo_url="https://cdn.x/logo.png",
        color_primary="#112233",
        color_secondary="#445566",
        app_name="I-Lex",
    )
    resp = await client.get(_CURRENT, headers=_host("ilex.autoken.es"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["logo_url"] == "https://cdn.x/logo.png"
    assert body["color_primary"] == "#112233"
    assert body["color_secondary"] == "#445566"
    assert body["app_name"] == "I-Lex"


async def test_s42_defensivo_sin_fila_de_tenant_branding_todos_los_campos_son_null(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """Defensivo: sin ninguna fila de `tenant_branding` (estado no alcanzable en producción, donde
    `create_tenant`, S4.1, siempre crea una), `get_branding` da `None` y el endpoint no rompe."""
    client, dsns = api
    await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    resp = await client.get(_CURRENT, headers=_host("ilex.autoken.es"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["logo_url"] is None
    assert body["color_primary"] is None
    assert body["color_secondary"] is None
    assert body["app_name"] is None
    assert body["favicon"] is None


async def test_s42_c2_alta_minima_via_platform_admin_app_name_cae_al_nombre_del_tenant(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """S4.2 C2 (camino real): un tenant dado de alta sin logo/colores (S4.1) siempre tiene fila de
    `tenant_branding`, con `app_name` = su `name` (no `null`) y el resto de branding a `null`."""
    client, dsns = api
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    create_resp = await client.post(
        "/api/v1/platform/tenants",
        json={"name": "Mínima SL", "slug": "minima"},
        headers={**_host("panel.localhost"), **bearer(token)},
    )
    assert create_resp.status_code == 201, create_resp.text

    resp = await client.get(_CURRENT, headers=_host("minima.autoken.es"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["app_name"] == "Mínima SL"
    assert body["logo_url"] is None
    assert body["color_primary"] is None
    assert body["color_secondary"] is None


async def test_s42_c3_sigue_siendo_404_neutro_sin_tenant(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """S4.2 C3: host que no resuelve -> 404, sin cambios por añadir branding a la respuesta."""
    client, _ = api
    resp = await client.get(_CURRENT, headers=_host("nope.autoken.es"))
    assert resp.status_code == 404


async def test_s42_c4_anticruce_branding_no_se_filtra_entre_tenants(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """S4.2 C4: el branding de `ilex` no aparece al pedir el de `otra`, y viceversa."""
    client, dsns = api
    tid_ilex = await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    tid_otra = await seed_tenant(dsns["admin"], "otra", "Otra Asesoría")
    await seed_branding(dsns["admin"], tenant_id=tid_ilex, app_name="I-Lex")
    await seed_branding(dsns["admin"], tenant_id=tid_otra, app_name="Otra")

    resp_ilex = await client.get(_CURRENT, headers=_host("ilex.autoken.es"))
    resp_otra = await client.get(_CURRENT, headers=_host("otra.autoken.es"))

    assert resp_ilex.json()["app_name"] == "I-Lex"
    assert resp_otra.json()["app_name"] == "Otra"


async def test_s42_rls_tapa_la_lectura_directa_de_tenant_branding_sin_contexto(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """S4.2 (defensa en profundidad, mismo patrón que C6): sin `app.tenant_id` fijado, un `SELECT`
    directo del rol runtime sobre `tenant_branding` no ve nada, aunque la fila exista de verdad.

    El test C4 (arriba) demuestra el comportamiento observable (branding correcto por subdominio),
    pero pasaría igual si la RLS de `tenant_branding` estuviera rota, porque el `WHERE` de la
    propia consulta ya filtra por el tenant correcto. Este test aísla la RLS como mecanismo, no el
    filtro de aplicación (regla de oro 5 del proyecto: la suite anti-cruce es gate bloqueante).
    """
    _, dsns = api
    tenant_id = await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    await seed_branding(dsns["admin"], tenant_id=tenant_id, app_name="I-Lex")
    conn = await asyncpg.connect(dsns["app"])  # rol runtime, sin app.tenant_id
    try:
        filas = await conn.fetch("SELECT * FROM tenant_branding WHERE tenant_id = $1", tenant_id)
    finally:
        await conn.close()
    assert len(filas) == 0  # RLS FORCE: sin contexto, 0 filas aunque la fila exista


# --- Refuerzos de la auditoría de S1.2 ----------------------------------------------------------


async def test_la_funcion_definer_es_propiedad_de_un_rol_bypassrls_no_superusuario(
    api: tuple[httpx.AsyncClient, dict[str, str]],
) -> None:
    """H1: `resolve_tenant` la posee un rol con BYPASSRLS y NO superusuario.

    Así funciona igual en producción (no depende de que el owner sea superusuario): si el owner no
    saltara la RLS, la función daría 0 filas para todo tenant y todos los subdominios darían 404.
    """
    conn = await asyncpg.connect(api[1]["admin"])
    try:
        row = await conn.fetchrow(
            "SELECT r.rolbypassrls, r.rolsuper FROM pg_proc p "
            "JOIN pg_roles r ON r.oid = p.proowner WHERE p.proname = 'resolve_tenant'"
        )
    finally:
        await conn.close()
    assert row is not None
    assert row["rolbypassrls"] is True
    assert row["rolsuper"] is False


async def test_fallo_de_bd_al_resolver_da_500_no_404(
    api: tuple[httpx.AsyncClient, dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo de infraestructura al resolver NO se enmascara como 'tenant inexistente' (§5)."""
    client, _ = api

    async def _boom(_slug: str) -> None:
        raise RuntimeError("BD caída")

    monkeypatch.setattr("shared.middleware.resolve_tenant", _boom)
    resp = await client.get(_CURRENT, headers=_host("ilex.autoken.es"))
    assert resp.status_code == 500


@pytest.mark.parametrize(
    ("host", "allow_localhost", "esperado"),
    [
        ("ilex.autoken.es", False, "ilex"),
        ("ILEX.AUTOKEN.ES", False, "ilex"),  # case-insensitive
        ("ilex.autoken.es.", False, "ilex"),  # FQDN con punto final
        ("ilex.autoken.es:8000", False, "ilex"),  # puerto ignorado
        # Prefijo multi-etiqueta bajo el dominio base -> rechazado (auditoría S1.6 A1): no se
        # colapsa a la primera etiqueta, que era la conducta insegura (un `Host` manipulado como
        # `a.b.autoken.es` no debe pasar por el tenant `a`).
        ("a.b.autoken.es", False, None),
        ("panel.foo.autoken.es", False, None),  # no es el panel canónico
        ("ilex.x.autoken.es", False, None),  # no es el tenant `ilex`
        ("autoken.es", False, None),  # raíz
        ("www.autoken.es", False, None),  # reservado
        ("panel.autoken.es", False, None),  # plataforma
        ("autoken.es.evil.com", False, None),  # dominio base en medio, no al final
        ("1.2.3.4", False, None),  # IP
        ("", False, None),  # host vacío
        ("ilex.localhost", True, "ilex"),  # localhost solo en desarrollo
        ("ilex.localhost", False, None),  # en producción, localhost no resuelve
    ],
)
def test_extract_subdomain(host: str, allow_localhost: bool, esperado: str | None) -> None:
    """`extract_subdomain` cubre los casos límite de la spec §5 (función pura, sin BD)."""
    from tenancy.resolution import extract_subdomain

    assert extract_subdomain(host, "autoken.es", allow_localhost=allow_localhost) == esperado

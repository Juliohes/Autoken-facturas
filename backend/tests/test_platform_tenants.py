"""Tests de comportamiento S4.1: alta y listado de tenants desde el panel de plataforma
(spec docs/specs/S4.1-alta-tenant.md). Criterios C1-C9.

Observable vía HTTP (cliente ASGI), autenticado como `platform_admin` (login real, S1.3), contra
Postgres real. Vector de autorización distinto al resto del proyecto: plataforma vs. tenant, no
tenant vs. tenant (por eso no vive en `test_tenant_isolation.py`).
"""

from __future__ import annotations

import httpx

from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, bearer, host, login
from tests._dbtest import seed_tenant, seed_user
from tests._platform import (
    count_tenants,
    fetch_branding,
    fetch_tenant_by_slug,
    platform_token,
    seed_platform_admin,
)

Api = tuple[httpx.AsyncClient, dict[str, str]]

URL = "/api/v1/platform/tenants"


def _auth(token: str) -> dict[str, str]:
    return {**host("panel.localhost"), **bearer(token)}


async def test_c1_alta_de_un_tenant_completo(authapi: Api) -> None:
    """C1: alta con nombre, slug, logo y 2 colores -> 201, tenant + branding persistidos."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(
        URL,
        json={
            "name": "Asesoría Nueva SL",
            "slug": "nueva",
            "logo_url": "https://cdn.x/logo.png",
            "color_primary": "#112233",
            "color_secondary": "#445566",
        },
        headers=_auth(token),
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "nueva"
    assert body["name"] == "Asesoría Nueva SL"
    assert body["status"] == "active"
    assert body["is_demo"] is False

    tenant = await fetch_tenant_by_slug(dsns, slug="nueva")
    assert tenant is not None
    branding = await fetch_branding(dsns, tenant_id=str(tenant["id"]))
    assert branding is not None
    assert branding["logo_url"] == "https://cdn.x/logo.png"
    assert branding["color_primary"] == "#112233"
    assert branding["color_secondary"] == "#445566"
    assert branding["app_name"] == "Asesoría Nueva SL"


async def test_c2_alta_minima_sin_branding(authapi: Api) -> None:
    """C2: solo nombre + slug -> 201; branding con logo/colores null, app_name = name."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(
        URL, json={"name": "Mínima SL", "slug": "minima"}, headers=_auth(token)
    )

    assert resp.status_code == 201, resp.text
    tenant = await fetch_tenant_by_slug(dsns, slug="minima")
    assert tenant is not None
    branding = await fetch_branding(dsns, tenant_id=str(tenant["id"]))
    assert branding is not None
    assert branding["logo_url"] is None
    assert branding["color_primary"] is None
    assert branding["color_secondary"] is None
    assert branding["app_name"] == "Mínima SL"


async def test_c3_slug_con_formato_invalido(authapi: Api) -> None:
    """C3: slug con mayúsculas/espacios o que empieza/termina en guión -> 422, nada se crea."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    before = await count_tenants(dsns)

    for bad_slug in ["Nueva Asesoria", "-nueva", "nueva-", "a" * 64]:
        resp = await client.post(URL, json={"name": "X", "slug": bad_slug}, headers=_auth(token))
        assert resp.status_code == 422, f"{bad_slug!r}: {resp.text}"

    assert await count_tenants(dsns) == before


async def test_c3b_nombre_vacio(authapi: Api) -> None:
    """C3b (spec §5): nombre vacío o solo espacios -> 422, nada se crea."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    before = await count_tenants(dsns)

    for bad_name in ["", "   "]:
        resp = await client.post(
            URL, json={"name": bad_name, "slug": "nombrevacio"}, headers=_auth(token)
        )
        assert resp.status_code == 422, f"{bad_name!r}: {resp.text}"

    assert await count_tenants(dsns) == before


async def test_c4_slug_reservado_de_plataforma(authapi: Api) -> None:
    """C4: slug=panel/www/panel-staging -> 422, nada se crea."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    before = await count_tenants(dsns)

    for reserved in ["panel", "www", "panel-staging"]:
        resp = await client.post(URL, json={"name": "X", "slug": reserved}, headers=_auth(token))
        assert resp.status_code == 422, f"{reserved!r}: {resp.text}"

    assert await count_tenants(dsns) == before


async def test_c5_slug_duplicado(authapi: Api) -> None:
    """C5: slug ya usado por otro tenant -> 409, no se crea un segundo."""
    client, dsns = authapi
    await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(URL, json={"name": "Otra Ilex", "slug": "ilex"}, headers=_auth(token))

    assert resp.status_code == 409, resp.text


async def test_c6_color_con_formato_invalido(authapi: Api) -> None:
    """C6: color_primary no hexadecimal -> 422, nada se crea."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    before = await count_tenants(dsns)

    resp = await client.post(
        URL,
        json={"name": "X", "slug": "coloreada", "color_primary": "azul"},
        headers=_auth(token),
    )

    assert resp.status_code == 422, resp.text
    assert await count_tenants(dsns) == before


async def test_c7_listado_mas_reciente_primero(authapi: Api) -> None:
    """C7: dos tenants creados en orden -> el listado los devuelve en orden inverso de alta."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    await client.post(URL, json={"name": "Primero", "slug": "primero"}, headers=_auth(token))
    await client.post(URL, json={"name": "Segundo", "slug": "segundo"}, headers=_auth(token))

    resp = await client.get(URL, headers=_auth(token))

    assert resp.status_code == 200, resp.text
    slugs = [t["slug"] for t in resp.json()]
    assert slugs.index("segundo") < slugs.index("primero")


async def test_c8_un_tenant_admin_no_puede_dar_de_alta_ni_listar(authapi: Api) -> None:
    """C8: token de `tenant_admin` -> 403 en POST y GET; nada se crea ni se filtra."""
    client, dsns = authapi
    tenant_id = await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email="admin@ilex.es",
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
    )
    login_resp = await login(client, "ilex.localhost", "admin@ilex.es", USER_PASSWORD)
    assert login_resp.status_code == 200, login_resp.text
    token = login_resp.json()["access_token"]

    resp_post = await client.post(URL, json={"name": "X", "slug": "colada"}, headers=_auth(token))
    resp_get = await client.get(URL, headers=_auth(token))

    assert resp_post.status_code == 403
    assert resp_get.status_code == 403
    assert await fetch_tenant_by_slug(dsns, slug="colada") is None


async def test_c9_sin_autenticar_no_hay_acceso(authapi: Api) -> None:
    """C9: sin token válido -> 401 en POST y GET."""
    client, _dsns = authapi

    resp_post = await client.post(
        URL, json={"name": "X", "slug": "y"}, headers=_auth("token-invalido")
    )
    resp_get = await client.get(URL, headers=_auth("token-invalido"))

    assert resp_post.status_code == 401
    assert resp_get.status_code == 401


async def test_c10_el_host_de_la_peticion_es_irrelevante_para_platform_admin(authapi: Api) -> None:
    """C10 (decisión de dominio 1): un token de `platform_admin` vale igual desde un subdominio de
    tenant que desde `panel`; la barrera es el rol del token, no el host."""
    client, dsns = authapi
    await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.get(URL, headers={**host("ilex.localhost"), **bearer(token)})

    assert resp.status_code == 200, resp.text


async def test_c11_un_token_de_platform_admin_no_sirve_en_un_endpoint_de_tenant(
    authapi: Api,
) -> None:
    """C11 (cruce de roles inverso a C8): un token de `platform_admin` no tiene tenant, así que
    `current_identity` lo rechaza (403) en cualquier endpoint de negocio de un tenant."""
    client, dsns = authapi
    await seed_tenant(dsns["admin"], "ilex", "I-Lex Asesoría")
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.get(
        "/api/v1/companies", headers={**host("ilex.localhost"), **bearer(token)}
    )

    assert resp.status_code == 403

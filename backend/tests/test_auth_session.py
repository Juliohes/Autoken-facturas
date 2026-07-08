"""Tests de comportamiento S1.3: sesión, frontera de tenant y efecto de la suspensión.

Spec: docs/specs/S1.3-auth-jwt-totp.md, criterios C9-C12, C23. Testigo protegido `GET /auth/me`.
Fase roja: los endpoints `/auth/*` aún no existen.
"""

from __future__ import annotations

import httpx

from tests._auth import ME, USER_PASSWORD, bearer, host, login, seed_active_user
from tests._dbtest import seed_tenant, suspend_tenant

Api = tuple[httpx.AsyncClient, dict[str, str]]


async def test_c9_access_token_identifica_y_token_manipulado_da_401(authapi: Api) -> None:
    """C9: el access token identifica en `/auth/me`; un token con la firma alterada da 401."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    resp = await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)
    assert resp.status_code == 200
    token = resp.json()["access_token"]

    ok = await client.get(ME, headers={**host("ilex.localhost"), **bearer(token)})
    assert ok.status_code == 200
    assert ok.json().get("email") == "ana@ilex.es"

    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    bad = await client.get(ME, headers={**host("ilex.localhost"), **bearer(tampered)})
    assert bad.status_code == 401


async def test_c10_endpoint_de_negocio_sin_token_da_401(authapi: Api) -> None:
    """C10: sin cabecera Authorization, un endpoint de negocio responde 401."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    resp = await client.get(ME, headers=host("ilex.localhost"))
    assert resp.status_code == 401


async def test_c11_token_de_otra_asesoria_en_este_subdominio_da_403(authapi: Api) -> None:
    """C11: un token cuyo tenant_id es ilex, usado en el subdominio de otro tenant activo -> 403."""
    client, dsns = authapi
    await seed_active_user(dsns, slug="ilex", email="ana@ilex.es")
    await seed_tenant(dsns["admin"], "otra", "Otra SL")  # tenant activo: su subdominio resuelve
    resp = await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    cruzado = await client.get(ME, headers={**host("otra.localhost"), **bearer(token)})
    assert cruzado.status_code == 403  # autenticado, pero el token no es de este subdominio


async def test_c12_con_el_token_correcto_la_peticion_corre_en_contexto_del_tenant(
    authapi: Api,
) -> None:
    """C12: con el token correcto, `/auth/me` lee bajo `tenant_session` (RLS del tenant A)."""
    client, dsns = authapi
    await seed_active_user(dsns, slug="ilex", email="ana@ilex.es", role="user")
    resp = await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    me = await client.get(ME, headers={**host("ilex.localhost"), **bearer(token)})
    assert me.status_code == 200
    assert me.json().get("tenant") == "ilex"
    assert me.json().get("role") == "user"


async def test_c23_suspender_el_tenant_invalida_la_sesion_al_instante(authapi: Api) -> None:
    """C23: al suspender el tenant, su subdominio deja de resolver y el token deja de valer."""
    client, dsns = authapi
    tenant_id, _ = await seed_active_user(dsns, slug="ilex", email="ana@ilex.es")
    resp = await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    antes = await client.get(ME, headers={**host("ilex.localhost"), **bearer(token)})
    assert antes.status_code == 200  # la sesión vale mientras el tenant está activo

    await suspend_tenant(dsns["admin"], tenant_id)

    despues = await client.get(ME, headers={**host("ilex.localhost"), **bearer(token)})
    assert despues.status_code in (401, 403)  # suspendido: el subdominio no resuelve -> sin sesión

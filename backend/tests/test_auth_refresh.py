"""Tests de comportamiento S1.3: refresh rotativo con detección de reuso y logout.

Spec: docs/specs/S1.3-auth-jwt-totp.md, criterios C13-C16. Fase roja: los endpoints `/auth/*` aún no
existen.
"""

from __future__ import annotations

import httpx

from tests._auth import (
    LOGOUT,
    REFRESH,
    REFRESH_COOKIE,
    USER_PASSWORD,
    host,
    login,
    refresh_cookie_of,
    seed_active_user,
)

Api = tuple[httpx.AsyncClient, dict[str, str]]


async def _login_ilex(client: httpx.AsyncClient) -> str:
    resp = await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)
    assert resp.status_code == 200
    cookie = refresh_cookie_of(resp)
    assert cookie
    return cookie


async def test_c13_refrescar_rota_el_token(authapi: Api) -> None:
    """C13: `/auth/refresh` con refresh válido -> nuevo access + nueva cookie de refresh."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    rt = await _login_ilex(client)
    ref = await client.post(REFRESH, cookies={REFRESH_COOKIE: rt}, headers=host("ilex.localhost"))
    assert ref.status_code == 200
    assert ref.json().get("access_token")
    nuevo_rt = refresh_cookie_of(ref)
    assert nuevo_rt and nuevo_rt != rt  # el refresh se ha rotado


async def test_c14_reusar_un_refresh_rotado_revoca_la_familia(authapi: Api) -> None:
    """C14: reusar un refresh ya rotado -> 401 y revoca la familia (el nuevo tampoco vale)."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    rt = await _login_ilex(client)
    ref = await client.post(REFRESH, cookies={REFRESH_COOKIE: rt}, headers=host("ilex.localhost"))
    assert ref.status_code == 200
    nuevo_rt = refresh_cookie_of(ref)

    reuso = await client.post(REFRESH, cookies={REFRESH_COOKIE: rt}, headers=host("ilex.localhost"))
    assert reuso.status_code == 401  # refresh viejo reutilizado

    tras = await client.post(
        REFRESH, cookies={REFRESH_COOKIE: nuevo_rt}, headers=host("ilex.localhost")
    )
    assert tras.status_code == 401  # la familia entera queda revocada


async def test_c15_refresh_ausente_o_manipulado_da_401(authapi: Api) -> None:
    """C15: sin cookie de refresh, o con una manipulada, `/auth/refresh` -> 401."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    ausente = await client.post(REFRESH, headers=host("ilex.localhost"))
    assert ausente.status_code == 401
    manipulado = await client.post(
        REFRESH, cookies={REFRESH_COOKIE: "no-es-un-token"}, headers=host("ilex.localhost")
    )
    assert manipulado.status_code == 401


async def test_revoke_all_sessions_invalida_el_refresh_sin_conocer_el_token(authapi: Api) -> None:
    """`revoke_all_sessions(user_id)` invalida el refresh vigente sin que nadie lo presente antes.

    Caso real: restablecer la contraseña por "olvidé mi contraseña" (bloque 1 del sistema de acceso
    completo) debe cerrar cualquier sesión abierta en OTRO dispositivo, del que no se tiene cookie.
    """
    from identity.sessions import revoke_all_sessions
    from shared.redis import get_redis

    client, dsns = authapi
    _tenant_id, user_id = await seed_active_user(dsns, email="ana@ilex.es")
    rt = await _login_ilex(client)

    await revoke_all_sessions(get_redis(), user_id, ttl_seconds=3600)

    tras = await client.post(REFRESH, cookies={REFRESH_COOKIE: rt}, headers=host("ilex.localhost"))
    assert tras.status_code == 401  # la sesión abierta antes del cambio deja de valer

    rt2 = await _login_ilex(client)  # una sesión nueva, iniciada DESPUÉS del cambio, sigue viva
    ref2 = await client.post(REFRESH, cookies={REFRESH_COOKIE: rt2}, headers=host("ilex.localhost"))
    assert ref2.status_code == 200


async def test_c16_logout_revoca_la_familia_y_borra_la_cookie(authapi: Api) -> None:
    """C16: `/auth/logout` revoca la familia y borra la cookie; sin cookie es idempotente."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    rt = await _login_ilex(client)

    out = await client.post(LOGOUT, cookies={REFRESH_COOKIE: rt}, headers=host("ilex.localhost"))
    assert out.status_code in (200, 204)
    assert REFRESH_COOKIE in out.headers.get("set-cookie", "")  # Set-Cookie que borra la cookie

    tras = await client.post(REFRESH, cookies={REFRESH_COOKIE: rt}, headers=host("ilex.localhost"))
    assert tras.status_code == 401  # el refresh ya no vale

    otra_vez = await client.post(LOGOUT, headers=host("ilex.localhost"))
    assert otra_vez.status_code in (200, 204)  # idempotente sin cookie

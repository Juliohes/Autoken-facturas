"""Hotfix (encontrado investigando S4.10, 2026-07-24): `GET /auth/me` usaba `current_identity`, que
exige un tenant resuelto por subdominio — un `platform_admin` (sin tenant, entra por `panel`)
recibía siempre 401. Regresión real desde que S4.9 (app-shell) empezó a llamar a `/auth/me`
también para el login de plataforma, no detectada porque los tests de frontend mockean el cliente
API. Reproducido de extremo a extremo contra el backend real antes de escribir este test.
"""

from __future__ import annotations

import httpx

from tests._auth import (
    ME,
    PLATFORM_PASSWORD,
    PLATFORM_PASSWORD_HASH,
    TOTP_SECRET,
    bearer,
    host,
    login,
    totp_now,
)
from tests._dbtest import seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]


async def test_platform_admin_puede_leer_su_propia_identidad_en_me(authapi: Api) -> None:
    """`GET /auth/me` tras un login de `platform_admin` responde 200 con su rol e id."""
    client, dsns = authapi
    await seed_user(
        dsns["admin"],
        tenant_id=None,
        email="julio@autoken.es",
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )
    login_resp = await login(
        client, "panel.localhost", "julio@autoken.es", PLATFORM_PASSWORD, totp_code=totp_now()
    )
    token = login_resp.json()["access_token"]

    resp = await client.get(ME, headers={**host("panel.localhost"), **bearer(token)})

    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "platform_admin"
    assert body["email"] == "julio@autoken.es"


async def test_me_de_platform_admin_no_tiene_tenant_ni_empresa(authapi: Api) -> None:
    """Un `platform_admin` no pertenece a ninguna asesoría: `tenant`/`company` vienen vacíos."""
    client, dsns = authapi
    await seed_user(
        dsns["admin"],
        tenant_id=None,
        email="julio@autoken.es",
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )
    login_resp = await login(
        client, "panel.localhost", "julio@autoken.es", PLATFORM_PASSWORD, totp_code=totp_now()
    )
    token = login_resp.json()["access_token"]

    resp = await client.get(ME, headers={**host("panel.localhost"), **bearer(token)})

    body = resp.json()
    assert body["tenant"] is None
    assert body["company"] is None


async def test_me_sin_token_de_platform_admin_sigue_dando_401(authapi: Api) -> None:
    """Sin cabecera de autenticación, `/auth/me` en el host de plataforma sigue exigiendo 401."""
    client, _dsns = authapi

    resp = await client.get(ME, headers=host("panel.localhost"))

    assert resp.status_code == 401

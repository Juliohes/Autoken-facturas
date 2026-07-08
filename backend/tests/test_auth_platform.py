"""Tests de comportamiento S1.3: login del administrador de plataforma por `panel`.

Spec: docs/specs/S1.3-auth-jwt-totp.md, criterio C18. El `platform_admin` no pertenece a ninguna
asesoría (`tenant_id` nulo) y se localiza por `find_platform_admin` (SECURITY DEFINER), sin
contexto de tenant. Fase roja: además de faltar los endpoints, sembrar un usuario con `tenant_id`
nulo falla hasta que exista la migración que lo permite (parte esperada del rojo).
"""

from __future__ import annotations

import asyncpg
import httpx

from tests._auth import PLATFORM_PASSWORD, PLATFORM_PASSWORD_HASH, TOTP_SECRET, login, totp_now
from tests._dbtest import seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]


async def test_c18_platform_admin_entra_por_panel_con_contrasena_y_totp(authapi: Api) -> None:
    """C18: `platform_admin` (sin tenant) hace login en `panel` con contraseña + TOTP -> 200."""
    client, dsns = authapi
    await seed_user(
        dsns["admin"],
        tenant_id=None,
        email="julio@autoken.es",
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )
    resp = await login(
        client, "panel.localhost", "julio@autoken.es", PLATFORM_PASSWORD, totp_code=totp_now()
    )
    assert resp.status_code == 200
    assert resp.json().get("access_token")


async def test_c18_el_rol_runtime_no_ve_al_platform_admin_por_seleccion_directa(
    authapi: Api,
) -> None:
    """C18: `find_platform_admin` es el único camino; el SELECT directo del runtime da 0 filas."""
    _, dsns = authapi
    await seed_user(
        dsns["admin"],
        tenant_id=None,
        email="julio@autoken.es",
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )
    conn = await asyncpg.connect(dsns["app"])  # rol runtime, sin contexto de tenant
    try:
        filas = await conn.fetch("SELECT * FROM users WHERE email = 'julio@autoken.es'")
    finally:
        await conn.close()
    assert len(filas) == 0  # la RLS tapa la lectura directa; solo la función acotada lo devuelve

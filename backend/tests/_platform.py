"""Utilidades de test del panel de plataforma (S4.1): sembrar y autenticar un `platform_admin`.

No es un módulo de tests (prefijo `_`): reutiliza tal cual los helpers de S1.3 (`seed_user` con
`tenant_id=None`, login con contraseña + TOTP en `panel.localhost`) para no repetir ese flujo en
cada test de `platform_admin`.
"""

from __future__ import annotations

import asyncpg
import httpx

from tests._auth import PLATFORM_PASSWORD, PLATFORM_PASSWORD_HASH, TOTP_SECRET, login, totp_now
from tests._dbtest import seed_user

PANEL_HOST = "panel.localhost"


async def seed_platform_admin(dsns: dict[str, str], *, email: str = "julio@autoken.es") -> str:
    """Siembra un `platform_admin` (sin tenant) con contraseña y TOTP ya listos. Devuelve su id."""
    return await seed_user(
        dsns["admin"],
        tenant_id=None,
        email=email,
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )


async def platform_token(client: httpx.AsyncClient, *, email: str = "julio@autoken.es") -> str:
    """Access token de un `platform_admin` ya sembrado (login real por `panel.localhost`)."""
    resp = await login(client, PANEL_HOST, email, PLATFORM_PASSWORD, totp_code=totp_now())
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def fetch_tenant_by_slug(dsns: dict[str, str], *, slug: str) -> dict | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow("SELECT * FROM tenants WHERE slug = $1", slug)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def fetch_branding(dsns: dict[str, str], *, tenant_id: str) -> dict | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow("SELECT * FROM tenant_branding WHERE tenant_id = $1", tenant_id)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def count_tenants(dsns: dict[str, str]) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(await conn.fetchval("SELECT count(*) FROM tenants"))
    finally:
        await conn.close()


async def fetch_tenant_by_id(dsns: dict[str, str], *, tenant_id: str) -> dict | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow("SELECT * FROM tenants WHERE id = $1", tenant_id)
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def count_companies(dsns: dict[str, str], *, tenant_id: str) -> int:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        return int(
            await conn.fetchval("SELECT count(*) FROM companies WHERE tenant_id = $1", tenant_id)
        )
    finally:
        await conn.close()


def bucket_exists(tenant_id: str) -> bool:
    """¿Existe el bucket de MinIO del tenant? (S4.4, import perezoso del almacén de producción)."""
    from invoice_intake import storage

    return storage._client().bucket_exists(storage.bucket_for(tenant_id))

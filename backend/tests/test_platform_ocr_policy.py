"""Tests HTTP de la política OCR de producción R-033."""

from __future__ import annotations

import httpx

from tests._auth import (
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
POLICY = "/api/v1/platform/ocr-policy"


async def _admin_token(client: httpx.AsyncClient, dsns: dict[str, str], *, tech: bool) -> str:
    await seed_user(
        dsns["admin"],
        tenant_id=None,
        email=f"policy-{tech}@autoken.es",
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
        is_admin_tech=tech,
    )
    response = await login(
        client,
        "panel.localhost",
        f"policy-{tech}@autoken.es",
        PLATFORM_PASSWORD,
        totp_code=totp_now(),
    )
    return response.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {**host("panel.localhost"), **bearer(token)}


async def test_r033_solo_admin_tech_puede_leer_la_politica(authapi: Api) -> None:
    client, dsns = authapi
    normal_token = await _admin_token(client, dsns, tech=False)
    tech_token = await _admin_token(client, dsns, tech=True)

    normal = await client.get(POLICY, headers=_headers(normal_token))
    tech = await client.get(POLICY, headers=_headers(tech_token))

    assert normal.status_code == 403
    assert tech.status_code == 200
    assert tech.json()["primary_engine"] == "gemini-3.5-flash"
    assert tech.json()["fallback_enabled"] is False


async def test_r033_cambiar_politica_exige_una_version_mayor(authapi: Api) -> None:
    client, dsns = authapi
    token = await _admin_token(client, dsns, tech=True)
    body = {
        "version": 2,
        "primary_engine": "gemini-3.6-flash",
        "primary_model": "gemini-3.6-flash",
        "fallback_enabled": False,
        "fallback_engine": "mistral-ocr-4",
        "fallback_model": "mistral-ocr-4-0",
        "consensus_mode": "primary_only",
    }

    updated = await client.put(POLICY, headers=_headers(token), json=body)
    stale = await client.put(POLICY, headers=_headers(token), json=body)

    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["primary_model"] == "gemini-3.6-flash"
    assert stale.status_code == 409

"""Tests de comportamiento: subida de logo de tenant como imagen (2026-08-01, decisión de Julio).

Observable vía HTTP (cliente ASGI), autenticado como `platform_admin`, contra Postgres/MinIO/
antivirus reales — mismo patrón que `test_intake_upload.py` (S2.1), del que se reutilizan los
ficheros de prueba (JPEG/PNG/EICAR válidos por número mágico).
"""

from __future__ import annotations

import httpx
import pytest

from tests._auth import USER_PASSWORD, USER_PASSWORD_HASH, bearer, host, login
from tests._dbtest import seed_tenant, seed_user
from tests._intake import EICAR_JPEG, JPEG, JPEG_CT, NOT_AN_IMAGE, PNG, PNG_CT
from tests._platform import platform_token, seed_platform_admin

Api = tuple[httpx.AsyncClient, dict[str, str]]

URL = "/api/v1/platform/tenants/logo"


def _auth(token: str) -> dict[str, str]:
    return {**host("panel.localhost"), **bearer(token)}


def _parts(content: bytes, *, filename: str, content_type: str) -> dict:
    return {"files": {"file": (filename, content, content_type)}}


async def test_c1_subir_jpeg_valido(authapi: Api) -> None:
    """C1: JPEG válido -> 201, URL pública devuelta, y esa URL es de verdad accesible sin sesión."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(
        URL, headers=_auth(token), **_parts(JPEG, filename="logo.jpg", content_type=JPEG_CT)
    )

    assert resp.status_code == 201, resp.text
    logo_url = resp.json()["logo_url"]
    assert logo_url.startswith("http")

    async with httpx.AsyncClient() as anon:
        public_resp = await anon.get(logo_url)
    assert public_resp.status_code == 200
    assert public_resp.content == JPEG


async def test_c2_subir_png_valido(authapi: Api) -> None:
    """C2: PNG válido se admite igual que JPEG."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(
        URL, headers=_auth(token), **_parts(PNG, filename="logo.png", content_type=PNG_CT)
    )

    assert resp.status_code == 201, resp.text


async def test_c3_tipo_no_admitido_se_rechaza(authapi: Api) -> None:
    """C3: un tipo que no es jpeg/png (decidido por los bytes, no por la cabecera) -> 415."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(
        URL,
        headers=_auth(token),
        **_parts(NOT_AN_IMAGE, filename="logo.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 415, resp.text


async def test_c4_fichero_vacio_se_rechaza(authapi: Api) -> None:
    """C4: fichero vacío -> 422."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(
        URL, headers=_auth(token), **_parts(b"", filename="logo.jpg", content_type=JPEG_CT)
    )

    assert resp.status_code == 422, resp.text


async def test_c5_fichero_demasiado_grande_se_rechaza(authapi: Api) -> None:
    """C5: por encima de MAX_LOGO_BYTES (2 MiB) -> 413."""
    from platform_admin.logo_upload import MAX_LOGO_BYTES

    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)
    oversized = JPEG[:-2] + b"\x00" * (MAX_LOGO_BYTES + 1) + b"\xff\xd9"

    resp = await client.post(
        URL, headers=_auth(token), **_parts(oversized, filename="logo.jpg", content_type=JPEG_CT)
    )

    assert resp.status_code == 413, resp.text


async def test_c6_fichero_infectado_se_rechaza(authapi: Api) -> None:
    """C6: firma EICAR embebida -> 422, sin exponer un objeto público infectado."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    resp = await client.post(
        URL,
        headers=_auth(token),
        **_parts(EICAR_JPEG, filename="logo.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 422, resp.text


async def test_c7_antivirus_no_disponible_fail_closed(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C7: si ClamAV no responde -> 503 (fail-closed), igual que el intake de facturas (S2.1)."""
    client, dsns = authapi
    await seed_platform_admin(dsns)
    token = await platform_token(client)

    from invoice_intake import scanner

    def _unavailable(_content: bytes) -> None:
        raise scanner.ScannerUnavailable("clamd caído (test)")

    monkeypatch.setattr(scanner, "scan", _unavailable)

    resp = await client.post(
        URL, headers=_auth(token), **_parts(JPEG, filename="logo.jpg", content_type=JPEG_CT)
    )

    assert resp.status_code == 503, resp.text


async def test_c8_sin_autenticar_no_se_sube(authapi: Api) -> None:
    """C8: sin token -> 401, no 201."""
    client, _dsns = authapi

    resp = await client.post(
        URL,
        headers=host("panel.localhost"),
        **_parts(JPEG, filename="logo.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 401, resp.text


async def test_c9_un_tenant_admin_no_puede_subir_logo(authapi: Api) -> None:
    """C9: el logo es cosa de plataforma (S4.1); un `tenant_admin` normal -> 403."""
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
    token = login_resp.json()["access_token"]

    resp = await client.post(
        URL,
        headers={**host("ilex.localhost"), **bearer(token)},
        **_parts(JPEG, filename="logo.jpg", content_type=JPEG_CT),
    )

    assert resp.status_code == 403, resp.text

"""Tests de comportamiento S4.10: interruptor admin-tech.

Spec: docs/specs/S4.10-interruptor-admin-tech.md, criterios C1-C7 (backend). `GET`/`PUT
/api/v1/platform/settings`, exclusivos de un `platform_admin` con el flag `is_admin_tech` activo.
"""

from __future__ import annotations

import httpx

from tests._auth import (
    PLATFORM_PASSWORD,
    PLATFORM_PASSWORD_HASH,
    TOTP_SECRET,
    USER_PASSWORD,
    USER_PASSWORD_HASH,
    bearer,
    host,
    login,
    totp_now,
)
from tests._dbtest import seed_tenant, seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]

SETTINGS = "/api/v1/platform/settings"
LAB_SETTINGS = "/api/v1/platform/ocr-lab/settings"


async def _login_platform_admin(
    client: httpx.AsyncClient, dsns: dict[str, str], *, is_admin_tech: bool, email: str
) -> str:
    await seed_user(
        dsns["admin"],
        tenant_id=None,
        email=email,
        role="platform_admin",
        password_hash=PLATFORM_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
        is_admin_tech=is_admin_tech,
    )
    resp = await login(client, "panel.localhost", email, PLATFORM_PASSWORD, totp_code=totp_now())
    assert resp.status_code == 200
    token: str = resp.json()["access_token"]
    return token


async def test_c1_platform_admin_sin_flag_no_puede_leer_ni_cambiar(authapi: Api) -> None:
    """C1: un `platform_admin` sin `is_admin_tech` recibe 403 en GET y PUT."""
    client, dsns = authapi
    token = await _login_platform_admin(
        client, dsns, is_admin_tech=False, email="alberto@autoken.es"
    )
    headers = {**host("panel.localhost"), **bearer(token)}

    get_resp = await client.get(SETTINGS, headers=headers)
    put_resp = await client.put(SETTINGS, headers=headers, json={"ocr_experiment_enabled": True})

    assert get_resp.status_code == 403
    assert put_resp.status_code == 403


async def test_c2_admin_tech_puede_leer_el_estado_por_defecto(authapi: Api) -> None:
    """C2: con el flag activo, GET responde 200 con `ocr_experiment_enabled: false` por defecto."""
    client, dsns = authapi
    token = await _login_platform_admin(client, dsns, is_admin_tech=True, email="julio@autoken.es")
    headers = {**host("panel.localhost"), **bearer(token)}

    resp = await client.get(SETTINGS, headers=headers)

    assert resp.status_code == 200
    assert resp.json() == {"ocr_experiment_enabled": False}


async def test_c3_tenant_admin_y_user_nunca_pueden(authapi: Api) -> None:
    """C3: un `tenant_admin`/`user` reciben 403 directamente contra `/platform/settings`."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")

    for role in ("tenant_admin", "user"):
        email = f"{role}@ilex.es"
        await seed_user(
            dsns["admin"], tenant_id=tid, email=email, role=role, password_hash=USER_PASSWORD_HASH
        )
        resp = await login(client, "ilex.localhost", email, USER_PASSWORD)
        token = resp.json()["access_token"]
        headers = {**host("ilex.localhost"), **bearer(token)}
        get_resp = await client.get(SETTINGS, headers=headers)
        assert get_resp.status_code == 403, f"{role}: {get_resp.status_code}"


async def test_c4_encender_el_interruptor(authapi: Api) -> None:
    """C4: PUT con `true` responde 200 y una lectura posterior confirma `true`."""
    client, dsns = authapi
    token = await _login_platform_admin(client, dsns, is_admin_tech=True, email="julio@autoken.es")
    headers = {**host("panel.localhost"), **bearer(token)}

    put_resp = await client.put(SETTINGS, headers=headers, json={"ocr_experiment_enabled": True})
    get_resp = await client.get(SETTINGS, headers=headers)

    assert put_resp.status_code == 200
    assert put_resp.json() == {"ocr_experiment_enabled": True}
    assert get_resp.json() == {"ocr_experiment_enabled": True}


async def test_c5_apagarlo_de_nuevo_es_idempotente(authapi: Api) -> None:
    """C5: apagar uno ya apagado también es 200 (idempotente), no un error."""
    client, dsns = authapi
    token = await _login_platform_admin(client, dsns, is_admin_tech=True, email="julio@autoken.es")
    headers = {**host("panel.localhost"), **bearer(token)}

    first = await client.put(SETTINGS, headers=headers, json={"ocr_experiment_enabled": False})
    second = await client.put(SETTINGS, headers=headers, json={"ocr_experiment_enabled": False})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"ocr_experiment_enabled": False}


async def test_c6_is_admin_tech_en_me_para_admin_tech(authapi: Api) -> None:
    """C6: `GET /auth/me` incluye `is_admin_tech: true` para quien de verdad tiene el flag."""
    client, dsns = authapi
    token = await _login_platform_admin(client, dsns, is_admin_tech=True, email="julio@autoken.es")

    resp = await client.get("/api/v1/auth/me", headers={**host("panel.localhost"), **bearer(token)})

    assert resp.status_code == 200
    assert resp.json()["is_admin_tech"] is True


async def test_c7_is_admin_tech_false_para_platform_admin_normal(authapi: Api) -> None:
    """C7: un `platform_admin` sin el flag ve `is_admin_tech: false` en `/auth/me`."""
    client, dsns = authapi
    token = await _login_platform_admin(
        client, dsns, is_admin_tech=False, email="alberto@autoken.es"
    )

    resp = await client.get("/api/v1/auth/me", headers={**host("panel.localhost"), **bearer(token)})

    assert resp.status_code == 200
    assert resp.json()["is_admin_tech"] is False


async def test_c11_admin_tech_ve_laboratorio_separado_y_apagado_por_defecto(authapi: Api) -> None:
    """R-046: el estado del laboratorio no comparte el booleano de producción legado."""
    client, dsns = authapi
    token = await _login_platform_admin(client, dsns, is_admin_tech=True, email="lab@autoken.es")

    resp = await client.get(LAB_SETTINGS, headers={**host("panel.localhost"), **bearer(token)})

    assert resp.status_code == 200
    assert resp.json() == {
        "lab_visible": False,
        "auto_benchmark_enabled": False,
        "benchmark_engines": ["tesseract"],
        "benchmark_variants": ["original", "enhanced", "clahe"],
    }


async def test_c12_desactivar_benchmark_automatico_no_toca_produccion(authapi: Api) -> None:
    """R-046: apagar el laboratorio persiste solo sus controles y mantiene la política fija."""
    client, dsns = authapi
    token = await _login_platform_admin(client, dsns, is_admin_tech=True, email="lab2@autoken.es")
    headers = {**host("panel.localhost"), **bearer(token)}

    lab_resp = await client.put(
        LAB_SETTINGS,
        headers=headers,
        json={
            "lab_visible": True,
            "auto_benchmark_enabled": False,
            "benchmark_engines": ["tesseract", "paddleocr"],
            "benchmark_variants": ["original", "clahe"],
        },
    )
    policy_resp = await client.get("/api/v1/platform/ocr-policy", headers=headers)

    assert lab_resp.status_code == 200
    assert lab_resp.json()["auto_benchmark_enabled"] is False
    assert policy_resp.status_code == 200
    assert policy_resp.json()["primary_engine"] == "gemini-3.5-flash"

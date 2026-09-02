"""Tests de comportamiento: recuperación de contraseña autoservicio (PROMPT-AUTOFACTU-AUTH-COMPLETO,
bloque 1). `POST /auth/password/forgot` es público en el subdominio y SIEMPRE responde igual, exista
o no la cuenta (anti-enumeración). `POST /auth/password/reset` fija la nueva contraseña con el token
recibido por email (aquí, capturado del `RecordingNotifier`) y cierra el resto de sesiones.
"""

from __future__ import annotations

import re

import httpx
import pytest

from tests._auth import (
    REFRESH,
    REFRESH_COOKIE,
    USER_PASSWORD,
    host,
    login,
    refresh_cookie_of,
    seed_active_user,
)

Api = tuple[httpx.AsyncClient, dict[str, str]]

FORGOT = "/api/v1/auth/password/forgot"
RESET = "/api/v1/auth/password/reset"
NEW_PASSWORD = "Un-Nuevo-Password-Seguro-99"  # gitleaks:allow


def _token_from_body(body: str) -> str:
    match = re.search(r"restablecer\?token=([^\s]+)", body)
    assert match, f"no se encontró un enlace de restablecimiento en: {body!r}"
    return match.group(1)


async def _forgot(
    client: httpx.AsyncClient, email: str, hostname: str = "ilex.localhost"
) -> httpx.Response:
    return await client.post(FORGOT, json={"email": email}, headers=host(hostname))


async def _issue_reset_token(
    client: httpx.AsyncClient, email: str, hostname: str = "ilex.localhost"
) -> str:
    """Pide el enlace de verdad (vía HTTP, como lo haría la persona) y extrae su token."""
    from notifications import get_notifier

    get_notifier().reset()
    resp = await _forgot(client, email, hostname)
    assert resp.status_code == 200, resp.text
    messages = get_notifier().messages
    assert len(messages) == 1
    assert messages[0].to == email
    return _token_from_body(messages[0].body)


async def test_forgot_con_cuenta_existente_envia_el_enlace_de_restablecimiento(
    authapi: Api,
) -> None:
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")

    token = await _issue_reset_token(client, "ana@ilex.es")
    assert token


async def test_forgot_con_email_inexistente_responde_igual_y_no_envia_nada(authapi: Api) -> None:
    """Anti-enumeración: mismo 200/cuerpo exista o no la cuenta; sin cuenta no se envía nada."""
    from notifications import get_notifier

    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    get_notifier().reset()

    existe = await _forgot(client, "ana@ilex.es")
    no_existe = await _forgot(client, "nadie@ilex.es")

    assert existe.status_code == no_existe.status_code == 200
    assert existe.json() == no_existe.json()
    assert len(get_notifier().messages) == 1  # solo el de la cuenta real


async def test_reset_con_token_valido_cambia_la_contrasena_y_permite_login_con_la_nueva(
    authapi: Api,
) -> None:
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    token = await _issue_reset_token(client, "ana@ilex.es")

    resp = await client.post(
        RESET, json={"token": token, "password": NEW_PASSWORD}, headers=host("ilex.localhost")
    )
    assert resp.status_code == 200, resp.text

    con_la_vieja = await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)
    assert con_la_vieja.status_code == 401
    con_la_nueva = await login(client, "ilex.localhost", "ana@ilex.es", NEW_PASSWORD)
    assert con_la_nueva.status_code == 200


async def test_reset_consume_el_token_de_un_solo_uso(authapi: Api) -> None:
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    token = await _issue_reset_token(client, "ana@ilex.es")

    primero = await client.post(
        RESET, json={"token": token, "password": NEW_PASSWORD}, headers=host("ilex.localhost")
    )
    assert primero.status_code == 200

    reuso = await client.post(
        RESET,
        json={"token": token, "password": "Otra-Password-Distinta-88"},
        headers=host("ilex.localhost"),
    )
    assert reuso.status_code == 401


async def test_reset_con_token_desconocido_da_401(authapi: Api) -> None:
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")

    resp = await client.post(
        RESET,
        json={"token": "esto-no-es-un-token-real", "password": NEW_PASSWORD},
        headers=host("ilex.localhost"),
    )
    assert resp.status_code == 401


async def test_reset_con_contrasena_debil_da_422(authapi: Api) -> None:
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    token = await _issue_reset_token(client, "ana@ilex.es")

    resp = await client.post(
        RESET, json={"token": token, "password": "corta"}, headers=host("ilex.localhost")
    )
    assert resp.status_code == 422


async def test_reset_revoca_las_sesiones_abiertas_en_otros_dispositivos(authapi: Api) -> None:
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")

    sesion_abierta = await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)
    assert sesion_abierta.status_code == 200
    refresh_token = refresh_cookie_of(sesion_abierta)
    assert refresh_token

    token = await _issue_reset_token(client, "ana@ilex.es")
    reset_resp = await client.post(
        RESET, json={"token": token, "password": NEW_PASSWORD}, headers=host("ilex.localhost")
    )
    assert reset_resp.status_code == 200

    tras_reset = await client.post(
        REFRESH, cookies={REFRESH_COOKIE: refresh_token}, headers=host("ilex.localhost")
    )
    assert tras_reset.status_code == 401


async def test_forgot_limitado_por_ip(authapi: Api, monkeypatch: pytest.MonkeyPatch) -> None:
    """Anti-spam: al superar el tope por IP, las siguientes solicitudes dan 429."""
    from shared import config

    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    monkeypatch.setenv("PASSWORD_RESET_MAX_PER_IP", "3")
    config.get_settings.cache_clear()

    try:
        for _ in range(3):
            resp = await _forgot(client, "ana@ilex.es")
            assert resp.status_code == 200
        extra = await _forgot(client, "ana@ilex.es")
        assert extra.status_code == 429
    finally:
        config.get_settings.cache_clear()


async def test_reset_con_token_de_otro_tenant_da_401(authapi: Api) -> None:
    """F2: un token sembrado en un tenant no vale presentado desde el subdominio de otro."""
    client, dsns = authapi
    await seed_active_user(dsns, slug="ilex", email="ana@ilex.es")
    await seed_active_user(dsns, slug="otra", email="ana@otra.es")
    token = await _issue_reset_token(client, "ana@ilex.es", hostname="ilex.localhost")

    cruzado = await client.post(
        RESET, json={"token": token, "password": NEW_PASSWORD}, headers=host("otra.localhost")
    )
    assert cruzado.status_code == 401

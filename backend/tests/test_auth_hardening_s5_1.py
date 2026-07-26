"""Tests de comportamiento S5.1: límites de intentos en endpoints sensibles sin rate-limit previo.

Spec: docs/specs/S5.1-cabeceras-y-limites.md, criterios C3-C8. `POST /auth/activate/confirm`
(fuerza bruta del TOTP de activación) y `POST /auth/refresh` (abuso de rotación) no tenían ningún
límite de intentos hasta esta tarea. Fase roja: el símbolo de configuración de los nuevos topes aún
no existe en `Settings`, así que el rate-limit tampoco actúa todavía.
"""

from __future__ import annotations

import asyncio
import os

import httpx

from tests._auth import (
    ACTIVATE,
    ACTIVATE_CONFIRM,
    REFRESH,
    REFRESH_COOKIE,
    USER_PASSWORD,
    host,
    login,
    refresh_cookie_of,
    secret_from_otpauth,
    seed_active_user,
    totp_now,
)
from tests._dbtest import seed_tenant, seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]

_ILEX_HOST = host("ilex.localhost")


async def _issue_activation_token(user_id: str) -> str:
    """Mismo seam que `test_auth_activation.py` (import perezoso: aún no existe en fase roja)."""
    from identity.activation import issue_activation_token

    return await issue_activation_token(user_id)


async def _activate_pending_confirmation(
    client: httpx.AsyncClient, admin_dsn: str, tenant_id: str, *, email: str
) -> tuple[str, str]:
    """Deja una cuenta del tenant `ilex` en 'contraseña fijada, TOTP sin confirmar' y devuelve
    `(token, secret)`. `tenant_id` ya debe existir (sembrado por el test llamador)."""
    uid = await seed_user(
        admin_dsn,
        tenant_id=tenant_id,
        email=email,
        role="tenant_admin",
        status="active",
        password_hash=None,
    )
    token = await _issue_activation_token(uid)
    activar = await client.post(
        ACTIVATE, json={"token": token, "password": USER_PASSWORD}, headers=_ILEX_HOST
    )
    assert activar.status_code == 200
    return token, secret_from_otpauth(activar.json()["otpauth_uri"])


async def _confirm(client: httpx.AsyncClient, token: str, code: str) -> httpx.Response:
    return await client.post(
        ACTIVATE_CONFIRM, json={"token": token, "totp_code": code}, headers=_ILEX_HOST
    )


async def test_c3_confirmar_activacion_limite_de_intentos_totp_por_token(authapi: Api) -> None:
    """C3: agotado el tope de códigos TOTP incorrectos para un token, el siguiente da 429 sin
    validar ya el código (ni aunque sea el correcto)."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    token, secret = await _activate_pending_confirmation(
        client, dsns["admin"], tid, email="a@ilex.es"
    )

    for _ in range(5):  # tope por defecto (`activation_confirm_max_attempts`)
        fallo = await _confirm(client, token, "000000")
        assert fallo.status_code == 401

    bloqueado = await _confirm(client, token, totp_now(secret))  # correcto, pero ya sin cupo
    assert bloqueado.status_code == 429


async def test_un_token_inexistente_tambien_cuenta_para_el_limite(authapi: Api) -> None:
    """Regresión (auditoría, invariante §4): un token FALSO también debe agotar su tope y dar 429,
    o el propio 429 revelaría que un token candidato es real (oráculo de enumeración)."""
    client, dsns = authapi
    await seed_tenant(dsns["admin"], "ilex", "I-Lex")

    for _ in range(5):
        fallo = await _confirm(client, "token-que-no-existe", "000000")
        assert fallo.status_code == 401

    bloqueado = await _confirm(client, "token-que-no-existe", "000000")
    assert bloqueado.status_code == 429


async def test_c4_confirmar_con_codigo_correcto_dentro_del_tope_funciona(authapi: Api) -> None:
    """C4: sin intentos fallidos previos, el código correcto activa la cuenta con normalidad."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    token, secret = await _activate_pending_confirmation(
        client, dsns["admin"], tid, email="a@ilex.es"
    )

    ok = await _confirm(client, token, totp_now(secret))
    assert ok.status_code == 200


async def test_c5_el_limite_de_activacion_es_por_token_no_global(authapi: Api) -> None:
    """C5: agotar el tope de un token no afecta al de otro usuario en activación simultánea."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    token_a, _secret_a = await _activate_pending_confirmation(
        client, dsns["admin"], tid, email="a@ilex.es"
    )
    token_b, secret_b = await _activate_pending_confirmation(
        client, dsns["admin"], tid, email="b@ilex.es"
    )

    for _ in range(5):
        assert (await _confirm(client, token_a, "000000")).status_code == 401
    assert (await _confirm(client, token_a, "000000")).status_code == 429  # A, agotado

    ok_b = await _confirm(client, token_b, totp_now(secret_b))  # B, intacto
    assert ok_b.status_code == 200


async def test_c6_pasada_la_ventana_de_activacion_se_vuelve_a_permitir(authapi: Api) -> None:
    """C6: agotado el tope, tras expirar la ventana un nuevo intento se evalúa con normalidad."""
    from shared import config

    client, dsns = authapi
    os.environ["ACTIVATION_CONFIRM_WINDOW_SECONDS"] = "1"
    config.get_settings.cache_clear()
    try:
        tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
        token, secret = await _activate_pending_confirmation(
            client, dsns["admin"], tid, email="a@ilex.es"
        )
        for _ in range(5):
            assert (await _confirm(client, token, "000000")).status_code == 401
        assert (await _confirm(client, token, totp_now(secret))).status_code == 429

        await asyncio.sleep(1.2)  # ventana de 1s ya expirada

        permitido = await _confirm(client, token, totp_now(secret))
        assert permitido.status_code == 200
    finally:
        os.environ.pop("ACTIVATION_CONFIRM_WINDOW_SECONDS", None)
        config.get_settings.cache_clear()


async def test_c7_refrescar_limite_de_intentos_por_ip(authapi: Api) -> None:
    """C7: agotado el tope de intentos de refresh fallidos por IP, el siguiente da 429."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")

    for _ in range(20):  # tope por defecto (`refresh_max_attempts`)
        fallo = await client.post(
            REFRESH, cookies={REFRESH_COOKIE: "token-invalido"}, headers=_ILEX_HOST
        )
        assert fallo.status_code == 401

    bloqueado = await client.post(
        REFRESH, cookies={REFRESH_COOKIE: "token-invalido"}, headers=_ILEX_HOST
    )
    assert bloqueado.status_code == 429


async def test_c8_refrescar_con_cookie_valida_dentro_del_tope_funciona(authapi: Api) -> None:
    """C8: por debajo del tope, un refresh válido rota el token con normalidad."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    login_resp = await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)
    rt = refresh_cookie_of(login_resp)
    assert rt

    ref = await client.post(REFRESH, cookies={REFRESH_COOKIE: rt}, headers=_ILEX_HOST)
    assert ref.status_code == 200
    assert ref.json().get("access_token")

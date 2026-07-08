"""Tests de comportamiento S1.3: primer acceso (activación de la cuenta).

Spec: docs/specs/S1.3-auth-jwt-totp.md, criterios C19-C21. La cuenta existe pero sin contraseña
(`password_hash IS NULL`); se activa con un token de activación de un solo uso. Fase roja: los
endpoints `/auth/activate*` no existen y la función de siembra del token (`identity.activation.
issue_activation_token`) tampoco (símbolo de dominio aún no implementado).
"""

from __future__ import annotations

import httpx

from tests._auth import (
    ACTIVATE,
    ACTIVATE_CONFIRM,
    PLATFORM_PASSWORD,
    USER_PASSWORD,
    USER_PASSWORD_HASH,
    host,
    login,
    secret_from_otpauth,
    totp_now,
)
from tests._dbtest import seed_tenant, seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]


async def _issue_activation_token(user_id: str) -> str:
    """Siembra el token de activación (en producción lo emite un script de plataforma).

    Import perezoso: en la fase roja el símbolo aún no existe y el test falla por dominio no
    implementado, no por un import roto del propio fichero de test.
    """
    from identity.activation import issue_activation_token

    return await issue_activation_token(user_id)


async def test_c19_activar_fija_la_contrasena_y_devuelve_el_qr(authapi: Api) -> None:
    """C19: `/auth/activate` con (token, contraseña válida) -> 200 con la URI otpauth para el QR."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    uid = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        status="active",
        password_hash=None,
    )
    token = await _issue_activation_token(uid)
    resp = await client.post(
        ACTIVATE, json={"token": token, "password": USER_PASSWORD}, headers=host("ilex.localhost")
    )
    assert resp.status_code == 200
    assert resp.json().get("otpauth_uri", "").startswith("otpauth://totp/")


async def test_c20_tenant_admin_puede_omitir_totp_y_entrar_solo_con_contrasena(
    authapi: Api,
) -> None:
    """C20: un tenant_admin puede activar sin confirmar TOTP y entrar solo con contraseña."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    uid = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        status="active",
        password_hash=None,
    )
    token = await _issue_activation_token(uid)
    activar = await client.post(
        ACTIVATE, json={"token": token, "password": USER_PASSWORD}, headers=host("ilex.localhost")
    )
    assert activar.status_code == 200
    # sin confirmar TOTP, el login solo-contraseña funciona (TOTP opcional para tenant_admin)
    entrar = await login(client, "ilex.localhost", "admin@ilex.es", USER_PASSWORD)
    assert entrar.status_code == 200
    assert entrar.json().get("access_token")


async def test_c20_confirmar_totp_cierra_la_activacion_y_el_token_es_de_un_solo_uso(
    authapi: Api,
) -> None:
    """C20: confirmar con TOTP activa la cuenta y consume el token (reutilizarlo -> 401)."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    uid = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        status="active",
        password_hash=None,
    )
    token = await _issue_activation_token(uid)
    activar = await client.post(
        ACTIVATE, json={"token": token, "password": USER_PASSWORD}, headers=host("ilex.localhost")
    )
    assert activar.status_code == 200
    secret = secret_from_otpauth(activar.json()["otpauth_uri"])

    confirmar = await client.post(
        ACTIVATE_CONFIRM,
        json={"token": token, "totp_code": totp_now(secret)},
        headers=host("ilex.localhost"),
    )
    assert confirmar.status_code == 200

    reuso = await client.post(
        ACTIVATE,
        json={"token": token, "password": "Otra-Password-123456"},
        headers=host("ilex.localhost"),
    )
    assert reuso.status_code == 401  # token de un solo uso, ya consumido

    entrar = await login(
        client, "ilex.localhost", "admin@ilex.es", USER_PASSWORD, totp_code=totp_now(secret)
    )
    assert entrar.status_code == 200  # ya activa, con TOTP enrolado


async def test_c20_platform_admin_no_puede_entrar_hasta_confirmar_totp(authapi: Api) -> None:
    """C20: un platform_admin no completa la activación (ni entra) hasta confirmar el TOTP."""
    client, dsns = authapi
    uid = await seed_user(
        dsns["admin"],
        tenant_id=None,
        email="julio@autoken.es",
        role="platform_admin",
        status="active",
        password_hash=None,
    )
    token = await _issue_activation_token(uid)
    activar = await client.post(
        ACTIVATE,
        json={"token": token, "password": PLATFORM_PASSWORD},
        headers=host("panel.localhost"),
    )
    assert activar.status_code == 200
    secret = secret_from_otpauth(activar.json()["otpauth_uri"])

    sin_confirmar = await login(
        client, "panel.localhost", "julio@autoken.es", PLATFORM_PASSWORD, totp_code=totp_now(secret)
    )
    assert sin_confirmar.status_code == 401  # aún no activa: falta confirmar el TOTP

    confirmar = await client.post(
        ACTIVATE_CONFIRM,
        json={"token": token, "totp_code": totp_now(secret)},
        headers=host("panel.localhost"),
    )
    assert confirmar.status_code == 200
    entrar = await login(
        client, "panel.localhost", "julio@autoken.es", PLATFORM_PASSWORD, totp_code=totp_now(secret)
    )
    assert entrar.status_code == 200


async def test_c21_la_password_debe_cumplir_la_politica(authapi: Api) -> None:
    """C21: una contraseña que no cumple la política (mínimo 12) -> 422 y la cuenta no se activa."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    uid = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        status="active",
        password_hash=None,
    )
    token = await _issue_activation_token(uid)
    resp = await client.post(
        ACTIVATE, json={"token": token, "password": "corta"}, headers=host("ilex.localhost")
    )
    assert resp.status_code == 422
    # no se activó: el login sigue fallando
    entrar = await login(client, "ilex.localhost", "admin@ilex.es", "corta")
    assert entrar.status_code == 401


async def test_f4_cuenta_no_activable_pendiente_no_se_puede_activar(authapi: Api) -> None:
    """F4: una cuenta que no es activable (status 'pending', gate de aprobación de S1.4) -> 401.

    Contrato "cuenta activable = status='active' + password_hash IS NULL" (ADR-0012). Aunque exista
    un token de activación válido, consumirlo sobre una cuenta pendiente no fija la contraseña.
    """
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    uid = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        status="pending",  # aún no aprobada: no es activable
        password_hash=None,
    )
    token = await _issue_activation_token(uid)
    resp = await client.post(
        ACTIVATE, json={"token": token, "password": USER_PASSWORD}, headers=host("ilex.localhost")
    )
    assert resp.status_code == 401  # el guard rechaza consumir el token en una cuenta no activable


async def test_f4_token_viejo_no_reescribe_contrasena_de_cuenta_ya_activada(authapi: Api) -> None:
    """F4: un token no puede sobreescribir la contraseña de una cuenta ya activada.

    Tras activar (fija la contraseña), presentar otro token de activación con otra contraseña debe
    fallar (401) y NO cambiar la contraseña vigente: el login sigue siendo con la original.
    """
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    uid = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        status="active",
        password_hash=None,
    )
    token = await _issue_activation_token(uid)
    activar = await client.post(
        ACTIVATE, json={"token": token, "password": USER_PASSWORD}, headers=host("ilex.localhost")
    )
    assert activar.status_code == 200

    otro_token = await _issue_activation_token(uid)
    reintento = await client.post(
        ACTIVATE,
        json={"token": otro_token, "password": "Otra-Password-Distinta-99"},
        headers=host("ilex.localhost"),
    )
    assert reintento.status_code == 401  # cuenta no activable (ya tiene contraseña)

    entrar = await login(client, "ilex.localhost", "admin@ilex.es", USER_PASSWORD)
    assert entrar.status_code == 200  # la contraseña original sigue vigente
    otra = await login(client, "ilex.localhost", "admin@ilex.es", "Otra-Password-Distinta-99")
    assert otra.status_code == 401


async def test_f3_enroll_totp_no_reescribe_un_secreto_ya_enrolado(authapi: Api) -> None:
    """F3: el guard `totp_secret IS NULL` impide re-enrolar un segundo factor ya establecido.

    Simétrico con el guard de la contraseña. Se ejerce directamente el acceso a datos: un intento de
    enrolar un secreto nuevo sobre una cuenta que YA tiene TOTP no cambia el secreto vigente.
    """
    import asyncpg

    from identity import repository

    _, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    uid = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        status="active",
        password_hash=USER_PASSWORD_HASH,
        totp_secret="FIRSTSECRET234567",
    )
    await repository.enroll_totp(uid, "SECONDSECRET99999")  # intento de re-enrolar: debe ser no-op

    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow("SELECT totp_secret FROM users WHERE id = $1", uid)
    finally:
        await conn.close()
    assert row is not None
    assert row["totp_secret"] == "FIRSTSECRET234567"  # el guard impidió sobreescribirlo

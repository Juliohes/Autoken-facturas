"""Tests de comportamiento S1.3: login, segundo factor y rate-limit.

Spec: docs/specs/S1.3-auth-jwt-totp.md, criterios C1-C8, C17, C22. Observable vía HTTP (cliente ASGI
con cabecera `Host`) contra un Postgres real; los usuarios se siembran como superusuario y la app se
conecta como el rol runtime. Fase roja: los endpoints `/auth/*` aún no existen.
"""

from __future__ import annotations

import httpx
import pytest

from tests._auth import (
    LOGIN,
    PLATFORM_PASSWORD_HASH,
    REFRESH_COOKIE,
    TOTP_SECRET,
    USER_PASSWORD,
    USER_PASSWORD_HASH,
    host,
    login,
    seed_active_user,
    totp_now,
)
from tests._dbtest import seed_tenant, seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]


async def test_c1_login_correcto_devuelve_access_y_cookie_de_refresh(authapi: Api) -> None:
    """C1: credenciales correctas -> 200 con access token y cookie httpOnly de refresh."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    resp = await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)
    assert resp.status_code == 200
    assert resp.json().get("access_token")
    set_cookie = resp.headers.get("set-cookie", "")
    assert REFRESH_COOKIE in set_cookie
    assert "httponly" in set_cookie.lower()


async def test_c2_password_incorrecta_da_401_neutro(authapi: Api) -> None:
    """C2: contraseña equivocada -> 401 neutro, sin access token ni cookie de refresh."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    resp = await login(client, "ilex.localhost", "ana@ilex.es", "contrasena-equivocada")
    assert resp.status_code == 401
    assert "access_token" not in resp.json()
    assert REFRESH_COOKIE not in resp.headers.get("set-cookie", "")


async def test_c3_email_inexistente_da_401_identico_a_password_mala(authapi: Api) -> None:
    """C3: email inexistente -> 401 idéntico (cuerpo y status) al de contraseña mala."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    mala = await login(client, "ilex.localhost", "ana@ilex.es", "contrasena-equivocada")
    inexistente = await login(client, "ilex.localhost", "nadie@ilex.es", "loquesea-123456")
    assert inexistente.status_code == mala.status_code == 401
    assert inexistente.text == mala.text  # indistinguibles desde fuera


async def test_c4_login_aislado_por_subdominio(authapi: Api) -> None:
    """C4: el mismo email en dos tenants son cuentas distintas; el login no se cruza."""
    client, dsns = authapi
    tid_ilex = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    tid_otra = await seed_tenant(dsns["admin"], "otra", "Otra SL")
    await seed_user(
        dsns["admin"], tenant_id=tid_ilex, email="ana@correo.es", password_hash=USER_PASSWORD_HASH
    )
    await seed_user(
        dsns["admin"],
        tenant_id=tid_otra,
        email="ana@correo.es",
        password_hash=PLATFORM_PASSWORD_HASH,
    )  # otra contraseña
    correcto = await login(client, "ilex.localhost", "ana@correo.es", USER_PASSWORD)
    cruzado = await login(client, "otra.localhost", "ana@correo.es", USER_PASSWORD)
    assert correcto.status_code == 200
    assert cruzado.status_code == 401  # en 'otra' esa contraseña no vale


async def test_c5_cuenta_no_activa_no_puede_entrar(authapi: Api) -> None:
    """C5: cuenta sin contraseña / pendiente -> 401 neutro (no revela el motivo)."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    await seed_user(
        dsns["admin"], tenant_id=tid, email="nuevo@ilex.es", status="pending", password_hash=None
    )
    resp = await login(client, "ilex.localhost", "nuevo@ilex.es", USER_PASSWORD)
    assert resp.status_code == 401
    assert "access_token" not in resp.json()


async def test_c6_totp_obligatorio_sin_codigo_pide_segundo_factor(authapi: Api) -> None:
    """C6: cuenta con TOTP enrolado y sin código -> 401 con marca `totp_required`, sin tokens."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )
    resp = await login(client, "ilex.localhost", "admin@ilex.es", USER_PASSWORD)
    assert resp.status_code == 401
    assert resp.json().get("totp_required") is True
    assert "access_token" not in resp.json()


async def test_c7_totp_valido_completa_el_login(authapi: Api) -> None:
    """C7: con el código TOTP válido del momento -> 200 con tokens."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )
    resp = await login(
        client, "ilex.localhost", "admin@ilex.es", USER_PASSWORD, totp_code=totp_now()
    )
    assert resp.status_code == 200
    assert resp.json().get("access_token")


async def test_c8_totp_invalido_rechaza_el_login(authapi: Api) -> None:
    """C8: un código TOTP incorrecto -> 401, sin tokens."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="admin@ilex.es",
        role="tenant_admin",
        password_hash=USER_PASSWORD_HASH,
        totp_secret=TOTP_SECRET,
    )
    valido = totp_now()
    malo = "000000" if valido != "000000" else "123456"  # garantizado distinto del código vigente
    resp = await login(client, "ilex.localhost", "admin@ilex.es", USER_PASSWORD, totp_code=malo)
    assert resp.status_code == 401
    assert "access_token" not in resp.json()


async def test_c17_rate_limit_bloquea_tras_5_fallos_por_ip_y_email(authapi: Api) -> None:
    """C17: 5 fallos (IP+email) -> el 6º intento da 429 aunque la contraseña sea correcta."""
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    for _ in range(5):
        fallo = await login(client, "ilex.localhost", "ana@ilex.es", "mala")
        assert fallo.status_code == 401
    sexto = await login(client, "ilex.localhost", "ana@ilex.es", USER_PASSWORD)  # correcta
    assert sexto.status_code == 429  # bloqueado; no revela que la contraseña era correcta


async def test_c22_tope_por_ip_frena_el_barrido_de_emails(authapi: Api) -> None:
    """C22: muchos emails con 1 fallo cada uno desde una IP superan el tope por IP -> 429."""
    client, dsns = authapi
    await seed_tenant(dsns["admin"], "ilex", "I-Lex")
    for i in range(20):  # tope por IP por defecto = 20 en la ventana
        fallo = await login(client, "ilex.localhost", f"user{i}@ilex.es", "loquesea-123456")
        assert fallo.status_code == 401
    extra = await login(client, "ilex.localhost", "otromas@ilex.es", "loquesea-123456")
    assert extra.status_code == 429  # bloqueado por IP, aunque el email sea nuevo


async def _fail_login(
    client: httpx.AsyncClient, email: str, xff: str, *, password: str = "mala"
) -> httpx.Response:
    """POST /auth/login con una cabecera `X-Forwarded-For` explícita (simula tráfico tras proxy)."""
    return await client.post(
        LOGIN,
        json={"email": email, "password": password},
        headers={**host("ilex.localhost"), "X-Forwarded-For": xff},
    )


async def test_b1_rate_limit_distingue_clientes_por_xff_de_proxy_de_confianza(
    authapi: Api, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1: con un proxy de confianza, el rate-limit usa la IP real del cliente, no la del proxy.

    El peer directo en los tests (ASGITransport) es 127.0.0.1; declarado proxy de confianza, la
    IP del rate-limit se deriva de `X-Forwarded-For`. Un cliente que agota sus intentos NO bloquea a
    otro cliente distinto (otra IP), aunque ambos lleguen por el mismo proxy.
    """
    from shared import config

    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1")
    config.get_settings.cache_clear()

    for _ in range(5):  # cliente A (203.0.113.7) agota su cupo
        assert (await _fail_login(client, "ana@ilex.es", "203.0.113.7")).status_code == 401
    bloqueado_a = await client.post(
        LOGIN,
        json={"email": "ana@ilex.es", "password": USER_PASSWORD},
        headers={**host("ilex.localhost"), "X-Forwarded-For": "203.0.113.7"},
    )
    assert bloqueado_a.status_code == 429  # cliente A bloqueado (aunque la contraseña sea correcta)

    otro_cliente = await _fail_login(client, "ana@ilex.es", "198.51.100.9")
    assert otro_cliente.status_code == 401  # cliente B (otra IP) NO está bloqueado: 401, no 429

    config.get_settings.cache_clear()


async def test_b1_xff_de_fuente_no_confiable_se_ignora(authapi: Api) -> None:
    """B1: sin proxies de confianza (por defecto), el XFF crudo se ignora: no evade el rate-limit.

    Si se confiara en el XFF crudo, un atacante rotaría la cabecera en cada intento y nunca llegaría
    al tope. Como el peer directo no es de confianza, todos los intentos cuentan al mismo cubo (la
    IP del peer), y el 6º da 429 pese a llegar con un XFF nuevo.
    """
    client, dsns = authapi
    await seed_active_user(dsns, email="ana@ilex.es")
    for i in range(5):  # cada intento finge una IP de cliente distinta vía XFF
        assert (await _fail_login(client, "ana@ilex.es", f"203.0.113.{i}")).status_code == 401
    sexto = await client.post(
        LOGIN,
        json={"email": "ana@ilex.es", "password": USER_PASSWORD},
        headers={**host("ilex.localhost"), "X-Forwarded-For": "203.0.113.99"},
    )
    assert sexto.status_code == 429  # el XFF no confiable no cambia el cubo: sigue bloqueado

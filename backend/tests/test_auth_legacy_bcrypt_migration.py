"""Tests de comportamiento: migración perezosa bcrypt -> Argon2id (migración 0022).

Cuentas reales importadas de Setex (`docs/export-migracion/2026-07-28/`): llegan con
`password_hash=NULL` y `legacy_bcrypt_hash` relleno (el bcrypt que ya guardaba Setex). En su primer
login tras la migración, `identity.service.authenticate` debe verificar contra ese bcrypt heredado
y, si coincide, generar el Argon2id en ese mismo instante y descartar el bcrypt — sin que el usuario
note ningún cambio ni tenga que restablecer su contraseña.
"""

from __future__ import annotations

import asyncpg
import bcrypt
import httpx

from tests._auth import TOTP_SECRET, USER_PASSWORD, USER_PASSWORD_HASH, login, totp_now
from tests._dbtest import seed_tenant, seed_user

Api = tuple[httpx.AsyncClient, dict[str, str]]

_LEGACY_PASSWORD = "Contrasena-Real-Setex-2026"  # gitleaks:allow
_LEGACY_BCRYPT_HASH = bcrypt.hashpw(
    _LEGACY_PASSWORD.encode("utf-8"), bcrypt.gensalt(rounds=12)
).decode("ascii")


async def _user_row(admin_dsn: str, user_id: str) -> asyncpg.Record:
    conn = await asyncpg.connect(admin_dsn)
    try:
        row = await conn.fetchrow(
            "SELECT password_hash, legacy_bcrypt_hash FROM users WHERE id = $1", user_id
        )
        assert row is not None
        return row
    finally:
        await conn.close()


async def test_c1_password_real_correcta_migra_a_argon2_y_entra(authapi: Api) -> None:
    """C1: contraseña real correcta contra el bcrypt heredado -> 200, y queda migrado a Argon2id."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "setex", "Setex")
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="cliente@setexextremadura.es",
        role="user",
        password_hash=None,
        legacy_bcrypt_hash=_LEGACY_BCRYPT_HASH,
    )

    resp = await login(client, "setex.localhost", "cliente@setexextremadura.es", _LEGACY_PASSWORD)

    assert resp.status_code == 200
    assert resp.json().get("access_token")

    row = await _user_row(dsns["admin"], user_id)
    assert row["legacy_bcrypt_hash"] is None  # el bcrypt heredado se descarta para siempre
    assert row["password_hash"] is not None
    assert row["password_hash"].startswith("$argon2id$")  # migrado de verdad, no solo copiado


async def test_c2_password_incorrecta_no_migra_y_da_401(authapi: Api) -> None:
    """C2: contraseña equivocada contra el bcrypt heredado -> 401, sin tocar los hashes."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "setex", "Setex")
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="cliente@setexextremadura.es",
        role="user",
        password_hash=None,
        legacy_bcrypt_hash=_LEGACY_BCRYPT_HASH,
    )

    resp = await login(client, "setex.localhost", "cliente@setexextremadura.es", "otra-cosa")

    assert resp.status_code == 401
    assert "access_token" not in resp.json()

    row = await _user_row(dsns["admin"], user_id)
    assert row["legacy_bcrypt_hash"] == _LEGACY_BCRYPT_HASH  # intacto, no se tocó
    assert row["password_hash"] is None  # no ha migrado


async def test_c3_segundo_login_ya_usa_argon2_sin_tocar_bcrypt(authapi: Api) -> None:
    """C3: tras migrar, un segundo login ya no depende del bcrypt (ruta normal de Argon2id)."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "setex", "Setex")
    await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="cliente@setexextremadura.es",
        role="user",
        password_hash=None,
        legacy_bcrypt_hash=_LEGACY_BCRYPT_HASH,
    )
    primero = await login(
        client, "setex.localhost", "cliente@setexextremadura.es", _LEGACY_PASSWORD
    )
    assert primero.status_code == 200

    segundo = await login(
        client, "setex.localhost", "cliente@setexextremadura.es", _LEGACY_PASSWORD
    )
    assert segundo.status_code == 200  # sigue entrando con la misma contraseña, ya vía Argon2id


async def test_c4_cuenta_ya_migrada_ignora_un_bcrypt_heredado_residual(authapi: Api) -> None:
    """C4 (defensivo): si por lo que sea quedara un `password_hash` Y un bcrypt a la vez, manda
    el Argon2id — el bcrypt heredado nunca se consulta cuando ya hay uno normal."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "setex", "Setex")

    await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="cliente@setexextremadura.es",
        role="user",
        password_hash=USER_PASSWORD_HASH,
        legacy_bcrypt_hash=_LEGACY_BCRYPT_HASH,  # residual, no debería usarse
    )

    con_password_vieja_del_bcrypt = await login(
        client, "setex.localhost", "cliente@setexextremadura.es", _LEGACY_PASSWORD
    )
    assert con_password_vieja_del_bcrypt.status_code == 401  # el bcrypt ya no cuenta

    con_password_argon2 = await login(
        client, "setex.localhost", "cliente@setexextremadura.es", USER_PASSWORD
    )
    assert con_password_argon2.status_code == 200


async def test_c5_platform_admin_tech_migra_por_panel_con_totp(authapi: Api) -> None:
    """C5: una cuenta `tech` de Setex (-> platform_admin) también migra sola, vía `panel` + TOTP."""
    client, dsns = authapi
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=None,
        email="soporte@autoken.es",
        role="platform_admin",
        password_hash=None,
        legacy_bcrypt_hash=_LEGACY_BCRYPT_HASH,
        totp_secret=TOTP_SECRET,
    )

    resp = await login(
        client,
        "panel.localhost",
        "soporte@autoken.es",
        _LEGACY_PASSWORD,
        totp_code=totp_now(),
    )

    assert resp.status_code == 200
    assert resp.json().get("access_token")

    row = await _user_row(dsns["admin"], user_id)
    assert row["legacy_bcrypt_hash"] is None
    assert row["password_hash"] is not None
    assert row["password_hash"].startswith("$argon2id$")


async def test_c6_cuenta_sin_ningun_hash_no_entra(authapi: Api) -> None:
    """C6 (sanity): cuenta sin Argon2id ni bcrypt heredado -> 401 neutro, igual que siempre."""
    client, dsns = authapi
    tid = await seed_tenant(dsns["admin"], "setex", "Setex")
    await seed_user(
        dsns["admin"],
        tenant_id=tid,
        email="pendiente@setexextremadura.es",
        role="user",
        password_hash=None,
        legacy_bcrypt_hash=None,
    )
    resp = await login(
        client, "setex.localhost", "pendiente@setexextremadura.es", "cualquier-cosa-123"
    )
    assert resp.status_code == 401
    assert "access_token" not in resp.json()

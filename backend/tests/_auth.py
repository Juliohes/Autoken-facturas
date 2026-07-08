"""Utilidades de test para el flujo de autenticación (S1.3, spec docs/specs/S1.3-auth-jwt-totp.md).

No es un módulo de tests (prefijo `_`): reúne constantes, un generador de códigos TOTP (RFC 6238,
sin dependencias, para no acoplar los tests a la librería de producción) y helpers HTTP de
login/refresh. Los hashes Argon2id son reales (verifican la contraseña) para que, cuando el
endpoint exista, los criterios felices pasen a verde.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time

import httpx

# --- Endpoints (contrato que el implementer debe respetar) --------------------------------------
API = "/api/v1"
LOGIN = f"{API}/auth/login"
REFRESH = f"{API}/auth/refresh"
LOGOUT = f"{API}/auth/logout"
ACTIVATE = f"{API}/auth/activate"
ACTIVATE_CONFIRM = f"{API}/auth/activate/confirm"
ME = f"{API}/auth/me"

REFRESH_COOKIE = "refresh_token"  # nombre de la cookie httpOnly del refresh

# --- Credenciales de prueba ---------------------------------------------------------------------
# Contraseñas y hashes Argon2id de PRUEBA (ficticios, verifican la contraseña de al lado). No son
# secretos reales: `# gitleaks:allow` evita el falso positivo del gate de secretos (regla de oro 6).
USER_PASSWORD = "Correct-Horse-Battery-Staple-12"  # gitleaks:allow
USER_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$C5s3P0PcL9ARsnuHcz3gDg$j8fLHGxUEbaSyG7IHyyx/G55A5LOG+o7bBGQPP0vNh4"  # noqa: E501  # gitleaks:allow
PLATFORM_PASSWORD = "Julio-Platform-Admin-2026!"  # gitleaks:allow
PLATFORM_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$BTfOJ+SrdHtyfcfZ/NMG9w$pQCVrWLWNSpXkCF73DvrOah/7TaZ3sTv//wg3zoRhbY"  # noqa: E501  # gitleaks:allow

# Secreto TOTP base32 fijo para las cuentas con segundo factor en los tests.
TOTP_SECRET = "JBSWY3DPEHPK3PXP"


def totp_now(secret_b32: str = TOTP_SECRET, *, at: float | None = None, step: int = 30) -> str:
    """Código TOTP de 6 dígitos (HMAC-SHA1, ventana de 30 s), como el de una app de autenticación.

    Coincide con los defaults de las librerías TOTP (pyotp), para que el código generado aquí sea
    el que producción espera. `at` permite fijar el instante (probar tolerancias de reloj).
    """
    key = base64.b32decode(secret_b32)
    counter = int((at if at is not None else time.time()) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % 1_000_000).zfill(6)


def host(hostname: str) -> dict[str, str]:
    return {"Host": hostname}


async def login(
    client: httpx.AsyncClient,
    hostname: str,
    email: str,
    password: str,
    *,
    totp_code: str | None = None,
) -> httpx.Response:
    """POST /auth/login en el subdominio `hostname`. Devuelve la respuesta cruda."""
    body: dict[str, str] = {"email": email, "password": password}
    if totp_code is not None:
        body["totp_code"] = totp_code
    return await client.post(LOGIN, json=body, headers=host(hostname))


def refresh_cookie_of(resp: httpx.Response) -> str | None:
    """Extrae el valor de la cookie de refresh emitida en una respuesta (o None si no hay)."""
    return resp.cookies.get(REFRESH_COOKIE)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def secret_from_otpauth(uri: str) -> str:
    """Extrae el parámetro `secret` de una URI `otpauth://totp/...?secret=...` (para el QR)."""
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(uri).query).get("secret", [""])[0]


async def seed_active_user(
    dsns: dict[str, str],
    *,
    slug: str = "ilex",
    name: str = "I-Lex Asesoría",
    email: str = "ana@ilex.es",
    role: str = "user",
    password_hash: str = USER_PASSWORD_HASH,
    totp_secret: str | None = None,
) -> tuple[str, str]:
    """Siembra un tenant y un usuario activos con contraseña. Devuelve (tenant_id, user_id)."""
    from tests._dbtest import seed_tenant, seed_user

    tenant_id = await seed_tenant(dsns["admin"], slug, name)
    user_id = await seed_user(
        dsns["admin"],
        tenant_id=tenant_id,
        email=email,
        role=role,
        password_hash=password_hash,
        totp_secret=totp_secret,
    )
    return tenant_id, user_id

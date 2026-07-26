"""Primer acceso: activación de la cuenta con token de un solo uso (S1.3, C19-C21).

Una cuenta **activable** existe, está `active` y aún no tiene contraseña (`password_hash IS NULL`);
la aprobación `pending`->`active` es gate de S1.4 (ver ADR-0012). Se activa con un token de
activación de un solo uso (TTL, por defecto 72 h) que en producción emite un script de plataforma
(la entrega por email es de S1.4). El flujo:

1. `issue_activation_token(user_id)` -> siembra el token en Redis (seam usado por los tests y por el
   script de siembra de `platform_admin`).
2. `POST /auth/activate {token, password}` -> fija el hash Argon2id y genera el secreto TOTP,
   devolviendo la URI `otpauth://` para el QR. La cuenta aún no puede hacer login con TOTP hasta
   confirmarlo (obligatorio para `platform_admin`).
3. `POST /auth/activate/confirm {token, totp_code}` -> valida el código, enrola el secreto TOTP en
   la cuenta y **consume** el token (reutilizarlo -> 401).

Guard defensivo (F4): consumir el token solo activa la cuenta si es activable; el guard vive en la
función SQL `activation_set_password` (`status = 'active' AND password_hash IS NULL`, atómico), de
modo que un token sembrado para una cuenta no activable (pendiente de aprobación o ya activada) no
hace nada -> `AccountNotActivatable` -> 401.

Las escrituras pasan por el repositorio (`identity.repository`), que encapsula las funciones
`SECURITY DEFINER`. Este módulo recibe el cliente `redis` por parámetro (DI homogénea con
`sessions.py`/`ratelimit.py`), sin alcanzar el singleton global por dentro salvo en el seam de
siembra, cuyos parámetros de infra son opcionales por conveniencia del script y los tests.
"""

from __future__ import annotations

import json
import secrets

import redis.asyncio as aioredis

from identity import ratelimit, repository, totp
from identity.passwords import hash_password
from shared.config import get_settings
from shared.redis import get_redis


class InvalidActivationToken(Exception):
    """El token de activación no existe, caducó o ya fue consumido (mismo trato: no revela cuál)."""


class AccountNotActivatable(Exception):
    """La cuenta no es activable: no existe, no está activa o ya tiene contraseña."""


class ActivationConfirmRateLimited(Exception):
    """Este token superó su tope de códigos TOTP incorrectos en la ventana vigente (S5.1 C3)."""


def _key(token: str) -> str:
    return f"activation:{token}"


async def issue_activation_token(
    user_id: str,
    *,
    redis: aioredis.Redis | None = None,
    ttl_seconds: int | None = None,
) -> str:
    """Siembra un token de activación de un solo uso para `user_id` y lo devuelve.

    Seam de dominio (lo usan el script de siembra de plataforma y los tests). No toca la BD: solo
    registra el token->user_id en Redis con TTL; la cuenta se resuelve (y su elegibilidad se
    comprueba) al **consumir** el token en `activate_account`. `redis`/`ttl_seconds` son opcionales:
    si no se inyectan, se resuelven de la infraestructura por defecto (conveniencia del seam).
    """
    client = redis if redis is not None else get_redis()
    ttl = ttl_seconds if ttl_seconds is not None else get_settings().activation_ttl
    token = secrets.token_urlsafe(32)
    record = json.dumps({"user_id": str(user_id)})
    await client.set(_key(token), record, ex=ttl)
    return token


async def activate_account(
    redis: aioredis.Redis, token: str, password: str, *, ttl_seconds: int
) -> str:
    """Fija la contraseña, genera el secreto TOTP y devuelve la URI `otpauth://` para el QR.

    No consume el token (el mismo token confirma después el TOTP). Lanza `InvalidActivationToken` si
    el token no vale y `AccountNotActivatable` si la cuenta no es activable (guard del repositorio).
    """
    raw = await redis.get(_key(token))
    if raw is None:
        raise InvalidActivationToken
    user_id = json.loads(raw)["user_id"]

    identity = await repository.set_activation_password(user_id, hash_password(password))
    if identity is None:
        raise AccountNotActivatable

    secret = totp.generate_secret()
    # Guarda el secreto pendiente junto al token: se enrola en la cuenta solo al confirmarlo, de
    # modo que un `platform_admin` (TOTP obligatorio) no puede hacer login hasta confirmar, y un
    # `tenant_admin` que omita la confirmación se queda con login solo-contraseña.
    await redis.set(
        _key(token),
        json.dumps({"user_id": user_id, "secret": secret}),
        ex=ttl_seconds,
    )
    return totp.provisioning_uri(secret, identity.email)


async def confirm_activation(
    redis: aioredis.Redis,
    token: str,
    totp_code: str,
    *,
    max_attempts: int,
    window_seconds: int,
) -> None:
    """Valida el código TOTP, enrola el secreto en la cuenta y consume el token (un solo uso).

    Lanza `InvalidActivationToken` si el token no vale, si aún no se activó la contraseña, o si el
    código TOTP no es válido (mismo trato: no distingue el motivo). Lanza
    `ActivationConfirmRateLimited` (S5.1 C3) si este token ya agotó su tope de intentos fallidos en
    la ventana vigente — en ese caso ni siquiera se llega a mirar el código, aunque fuera el
    correcto (C3). El contador es por token (C5): agotar el de uno no bloquea a otro usuario.

    Un token desconocido/caducado/consumido TAMBIÉN cuenta como fallo (auditoría, invariante §4):
    si solo contaran los códigos incorrectos contra un token real, un `429` revelaría por sí mismo
    que el token existe (un token falso nunca llegaría a agotar su tope) — el mismo oráculo de
    enumeración que la spec prohíbe explícitamente. Con el token de 256 bits (`secrets.
    token_urlsafe(32)`) enumerarlo es inviable en la práctica, pero contar también este caso lo
    cierra sin coste real (la clave de un token falso expira igual que cualquier otra, TTL
    garantizado por el script atómico).
    """
    if await ratelimit.activation_confirm_blocked(redis, token, max_attempts=max_attempts):
        raise ActivationConfirmRateLimited

    raw = await redis.get(_key(token))
    if raw is None:
        await ratelimit.record_activation_confirm_failure(
            redis, token, window_seconds=window_seconds
        )
        raise InvalidActivationToken
    data = json.loads(raw)
    secret = data.get("secret")
    if secret is None or not totp.verify_code(secret, totp_code):
        await ratelimit.record_activation_confirm_failure(
            redis, token, window_seconds=window_seconds
        )
        raise InvalidActivationToken

    await repository.enroll_totp(data["user_id"], secret)
    await redis.delete(_key(token))

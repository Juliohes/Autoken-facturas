"""Casos de uso de autenticación (S1.3): orquestación de dominio, sin acoplarse a HTTP.

`authenticate` reúne la lógica de login —rate-limit, carga del usuario, verificación de contraseña,
decisión de segundo factor y emisión del refresh— y devuelve un **resultado de dominio tipado**. El
router HTTP solo traduce ese resultado a una respuesta (200 / 401 neutro / 401 `totp_required` /
429). Ni SQL ni cabeceras HTTP aquí.

Cualquier `RedisError` se deja propagar: el mapeo a 503 (fallo cerrado, §5) es responsabilidad de la
capa HTTP (`redis_guard` en el router), en un solo sitio.
"""

from __future__ import annotations

from dataclasses import dataclass

import redis.asyncio as aioredis

from identity import passwords, ratelimit, sessions
from identity.repository import AuthUser, load_for_login
from identity.totp import verify_code
from shared.config import Settings
from tenancy.constants import Role, UserStatus
from tenancy.resolution import ResolvedTenant


@dataclass(frozen=True)
class LoginSucceeded:
    """Credenciales válidas: identidad para el access token + el refresh recién emitido."""

    user_id: str
    tenant_id: str | None
    role: str
    refresh_token: str


@dataclass(frozen=True)
class TotpRequired:
    """Falta el segundo factor (rol con TOTP obligatorio/enrolado que no envió código)."""


@dataclass(frozen=True)
class NeutralFailure:
    """Fallo anti-enumeración: credenciales malas, email inexistente o cuenta no activa (401)."""


@dataclass(frozen=True)
class RateLimited:
    """El par (IP+email) o la IP han superado su tope: bloqueo temporal (429)."""


LoginResult = LoginSucceeded | TotpRequired | NeutralFailure | RateLimited


def _requires_totp(user: AuthUser) -> bool:
    """El segundo factor es obligatorio para `platform_admin` y para quien tenga TOTP enrolado."""
    return user.totp_secret is not None or user.role == Role.PLATFORM_ADMIN


async def authenticate(
    redis: aioredis.Redis,
    *,
    resolved: ResolvedTenant | None,
    ip: str,
    email: str,
    password: str,
    totp_code: str | None,
    settings: Settings,
) -> LoginResult:
    """Autentica email + contraseña (+ TOTP si aplica) y devuelve un resultado de dominio tipado."""
    if await ratelimit.is_blocked(
        redis,
        ip,
        email,
        max_per_email=settings.login_max_attempts,
        max_per_ip=settings.login_ip_max_attempts,
    ):
        return RateLimited()

    async def record_failure() -> None:
        """Suma el intento fallido a los contadores (mismo IP+email en las dos ramas de fallo)."""
        await ratelimit.record_failure(
            redis, ip, email, window_seconds=settings.login_window_seconds
        )

    user = await load_for_login(resolved, email)

    # La política de contraseña acota la longitud ANTES de hashear (defensa DoS). Si pasa, se hashea
    # siempre (con hash señuelo si no hay usuario) para no filtrar por latencia si el email existe.
    password_ok = passwords.validate_password_policy(
        password, settings
    ) and passwords.verify_password(password, user.password_hash if user is not None else None)
    if user is None or user.status != UserStatus.ACTIVE or not password_ok:
        await record_failure()
        return NeutralFailure()

    if _requires_totp(user):
        if user.totp_secret is None:
            # Rol con TOTP obligatorio aún no enrolado (activación sin confirmar): no puede entrar.
            return NeutralFailure()
        if totp_code is None:
            return TotpRequired()
        if not verify_code(user.totp_secret, totp_code):
            await record_failure()
            return NeutralFailure()

    await ratelimit.reset(redis, ip, email)
    refresh_token = await sessions.issue_refresh_token(
        redis,
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        ttl_seconds=settings.jwt_refresh_ttl,
    )
    return LoginSucceeded(
        user_id=user.id,
        tenant_id=user.tenant_id,
        role=user.role,
        refresh_token=refresh_token,
    )

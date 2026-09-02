"""Recuperación de contraseña autoservicio (PROMPT-AUTOFACTU-AUTH-COMPLETO, bloque 1).

Dos pasos, cada uno con su propio token de un solo uso en Redis (mismo patrón que `activation.py`):

1. `request_reset` (`POST /auth/password/forgot {email}`): si el email existe en el tenant del
   subdominio, está activo y ya tiene contraseña, siembra un token de restablecimiento ligado a
   user_id+tenant_id y avisa por email (`Notifier`). SIEMPRE se comporta igual exista o no la
   cuenta (anti-enumeración): el router responde con el mismo mensaje genérico en los dos casos.
2. `reset_password` (`POST /auth/password/reset {token, password}`): valida el token, aplica la
   política de contraseña, fija el hash (función SQL acotada `password_reset_set_password`, guard
   "activa y ya tenía contraseña"), CONSUME el token y revoca todas las sesiones abiertas del
   usuario (cambio de contraseña = cierre de sesión en cualquier otro dispositivo, `identity.
   sessions.revoke_all_sessions`).

A diferencia de la activación (gobernada por un script de operador), aquí el propio usuario pide su
token: el rate-limit por (IP+email) e IP (`ratelimit.password_reset_attempt_exceeds`) es la única
defensa entre este endpoint público y un vaciado de la bandeja de nadie a base de solicitudes.
"""

from __future__ import annotations

import json
import secrets
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from identity import password_reset_repo, ratelimit, repository
from identity.passwords import hash_password, validate_password_policy
from identity.sessions import revoke_all_sessions
from notifications import Message, Notifier
from shared.audit import write_audit
from shared.config import Settings

_AUDIT_ENTITY = "user"
AUDIT_ACTION_REQUESTED = "user.password_reset_requested"
AUDIT_ACTION_RESET = "user.password_reset"


class InvalidResetToken(Exception):
    """El token de restablecimiento no existe, caducó, ya fue consumido, o la cuenta ya no es
    restablecible (mismo trato: no revela cuál de los motivos fue) (-> 401)."""


class WeakPassword(Exception):
    """La nueva contraseña no cumple la política (-> 422)."""


class PasswordResetRateLimited(Exception):
    """El par (IP+email) o la IP han superado el tope de solicitudes de la ventana (-> 429)."""


def _key(token: str) -> str:
    return f"pwreset:{token}"


def _reset_url(settings: Settings, *, slug: str, token: str) -> str:
    """Enlace de restablecimiento, siempre al subdominio del propio tenant (nunca cruzado)."""
    return f"https://{slug}.{settings.base_domain}/restablecer?token={token}"


async def request_reset(
    session: AsyncSession,
    *,
    redis: aioredis.Redis,
    ip: str,
    tenant_id: UUID,
    tenant_slug: str,
    email: str,
    settings: Settings,
    notifier: Notifier,
) -> None:
    """Solicita el restablecimiento: SIEMPRE se comporta igual, exista o no la cuenta.

    Limita por (IP+email) e IP (429) ANTES de mirar nada más (mismo criterio que el registro):
    cuenta CADA solicitud, no solo las que encuentran cuenta real -- si solo contara cuando la
    cuenta existe, el propio 429 sería un oráculo de enumeración. Si la cuenta existe y es
    restablecible, siembra el token y avisa por email tras el commit (post-commit, igual que el
    aviso de registro); si no, no hace nada más -- el router responde igual en los dos casos.
    """
    if await ratelimit.password_reset_attempt_exceeds(
        redis,
        ip,
        email,
        max_per_email=settings.password_reset_max_per_email,
        max_per_ip=settings.password_reset_max_per_ip,
        window_seconds=settings.password_reset_window_seconds,
    ):
        raise PasswordResetRateLimited

    user = await password_reset_repo.find_resettable_user(session, email)
    if user is None:
        return  # anti-enumeración: ni se siembra token ni se avisa a nadie

    token = secrets.token_urlsafe(32)
    record = json.dumps({"user_id": str(user.id), "tenant_id": str(tenant_id)})
    await redis.set(_key(token), record, ex=settings.password_reset_ttl)
    await write_audit(
        session,
        actor_id=user.id,
        action=AUDIT_ACTION_REQUESTED,
        entity=_AUDIT_ENTITY,
        entity_id=user.id,
    )
    notifier.send(
        Message(
            to=email,
            subject="Restablece tu contraseña de Autofactu",
            body=(
                "Hemos recibido una solicitud para restablecer tu contraseña. Si has sido tú, "
                f"abre este enlace (caduca en {settings.password_reset_ttl // 60} minutos): "
                f"{_reset_url(settings, slug=tenant_slug, token=token)}\n\n"
                "Si no has sido tú, puedes ignorar este mensaje: tu contraseña actual sigue "
                "siendo válida."
            ),
            kind="password_reset",
        )
    )


async def reset_password(
    redis: aioredis.Redis,
    audit_session: AsyncSession,
    *,
    token: str,
    password: str,
    expected_tenant_id: UUID,
    settings: Settings,
) -> None:
    """Valida el token, fija la nueva contraseña, lo consume y cierra el resto de sesiones.

    `audit_session` es una sesión de tenant YA abierta en el contexto del subdominio por el que
    llega la petición (el router la abre igual que `PublicTenantContext`, `tenant_session(resolved.
    id)`): la escritura de la contraseña en sí pasa por la función `SECURITY DEFINER` (sin RLS,
    gobernada solo por el token), pero la auditoría necesita un `app.tenant_id` real para la RLS de
    `audit_log`. `expected_tenant_id` (F2, defensa en profundidad, mismo criterio que el refresh) es
    el tenant resuelto de ESE subdominio: si no casa con el `tenant_id` grabado en el token al
    sembrarlo, se trata como token inválido y no se toca nada -- un token robado y presentado desde
    el subdominio de OTRA asesoría no vale, aunque el token en sí siga siendo válido en el suyo.
    """
    if not validate_password_policy(password, settings):
        raise WeakPassword

    raw = await redis.get(_key(token))
    if raw is None:
        raise InvalidResetToken
    data = json.loads(raw)
    if data["tenant_id"] != str(expected_tenant_id):
        raise InvalidResetToken
    user_id = data["user_id"]

    identity = await repository.set_reset_password(user_id, hash_password(password))
    if identity is None:
        raise InvalidResetToken
    await redis.delete(_key(token))

    await revoke_all_sessions(redis, user_id, ttl_seconds=settings.jwt_refresh_ttl)
    await write_audit(
        audit_session,
        actor_id=UUID(user_id),
        action=AUDIT_ACTION_RESET,
        entity=_AUDIT_ENTITY,
        entity_id=UUID(user_id),
    )

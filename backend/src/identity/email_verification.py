"""Verificación del email del registrante (PROMPT-AUTOFACTU-AUTH-COMPLETO, bloque 2).

Complementa el aviso al `tenant_admin` (S1.4): además de avisarle de que hay un registro pendiente,
se manda al propio registrante un enlace de un solo uso para confirmar que el email es suyo de
verdad (reduce altas con emails ajenos y spam). NO bloquea la aprobación del admin -- es solo
información añadida (`email_verified` en `GET /registrations`), nunca un requisito para aprobar
(spec explícita del prompt): un admin puede aprobar un registro con el email todavía sin confirmar,
igual que podía antes de que existiera este flujo.

Mismo patrón de token de un solo uso que `activation.py`/`password_reset.py`: Redis, TTL, F2 (el
tenant del token debe casar con el del subdominio que lo presenta).
"""

from __future__ import annotations

import json
import secrets
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from identity import registration_repo
from shared.config import Settings


class InvalidVerificationToken(Exception):
    """El token de verificación no existe, caducó, ya fue consumido, o es de otro tenant (F2)."""


def _key(token: str) -> str:
    return f"emailverify:{token}"


async def issue_verification_token(
    redis: aioredis.Redis, *, user_id: UUID, tenant_id: UUID, ttl_seconds: int
) -> str:
    """Siembra un token de verificación de un solo uso ligado a user_id+tenant_id."""
    token = secrets.token_urlsafe(32)
    record = json.dumps({"user_id": str(user_id), "tenant_id": str(tenant_id)})
    await redis.set(_key(token), record, ex=ttl_seconds)
    return token


def verification_url(settings: Settings, *, slug: str, token: str) -> str:
    """Enlace de verificación, siempre al subdominio del propio tenant (nunca cruzado)."""
    return f"https://{slug}.{settings.base_domain}/registro/confirmar?token={token}"


async def verify_email(
    redis: aioredis.Redis,
    session: AsyncSession,
    *,
    token: str,
    expected_tenant_id: UUID,
) -> None:
    """Marca el email del registrante como verificado y consume el token.

    F2 (defensa en profundidad, mismo criterio que `password_reset.reset_password`): si el
    `tenant_id` grabado en el token no casa con `expected_tenant_id` (el resuelto del subdominio por
    el que llega la petición), se trata como token inválido y no se toca nada.
    """
    raw = await redis.get(_key(token))
    if raw is None:
        raise InvalidVerificationToken
    data = json.loads(raw)
    if data["tenant_id"] != str(expected_tenant_id):
        raise InvalidVerificationToken
    await registration_repo.mark_email_verified(session, UUID(data["user_id"]))
    await redis.delete(_key(token))

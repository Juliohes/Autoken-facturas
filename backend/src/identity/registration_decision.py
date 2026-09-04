"""Decisión de un alta pendiente por email, sin iniciar sesión (a petición de Julio, 2026-09-03,
sustituye la verificación de email del registrante del bloque 2 original de PROMPT-AUTOFACTU-
AUTH-COMPLETO: el registrante no necesita hacer nada, y los admins pueden decidir directamente
desde su bandeja, no solo desde el panel).

Cada `tenant_admin` avisado recibe SU PROPIO enlace de un solo uso (`registration.
_admin_messages`), ligado a user_id+tenant_id (F2) y a quién decide (para que la auditoría
atribuya la decisión al admin correcto, igual que si hubiera entrado por el panel).

Dos pasos, igual que activation.py separa "fijar contraseña" de "confirmar TOTP":
1. `peek` (GET, sin mutar nada): lo que ve la pantalla de confirmación antes de decidir.
2. `decide` (POST, la única que muta): aplica la decisión y consume el token.

La separación es una defensa real (F5), no un capricho: los clientes de correo y los antivirus
"previsitan" automáticamente los enlaces de un email para escanearlos en busca de malware. Si
aprobar/rechazar fuera una acción de un solo GET, ese escaneo automático podría decidir altas sin
que ningún humano lo pidiera. Con `peek` inocuo y `decide` exigiendo un POST explícito (el botón de
la pantalla de confirmación), un simple prefetch de enlace nunca llega a mutar nada.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from companies.service import tenant_encryption_key as company_encryption_key
from identity import registration_repo
from shared.config import Settings

Decision = Literal["approve", "reject"]

_KEY_PREFIX = "regdecision:"


class InvalidDecisionToken(Exception):
    """El enlace no existe, caducó, ya se consumió, o es de otro tenant (F2) (-> 401).

    También cubre, sin poder distinguirlo (a propósito, mismo criterio anti-enumeración que el
    resto de tokens de un solo uso de la app): un registro que ya fue RECHAZADO, porque rechazar
    borra la fila (`registration.reject`) y no queda nada que `peek`/`decide` puedan encontrar.
    """


@dataclass(frozen=True)
class DecisionSummary:
    """Lo que ve la pantalla de confirmación: a quién decide, y si ya no hace falta (otro admin, o
    el propio panel, ya decidieron mientras tanto)."""

    email: str
    company: str | None
    already_decided: bool


def _key(token: str) -> str:
    return f"{_KEY_PREFIX}{token}"


def decision_url(settings: Settings, *, slug: str, token: str) -> str:
    """Enlace de decisión, siempre al subdominio del propio tenant (nunca cruzado)."""
    return f"https://{slug}.{settings.base_domain}/decidir-alta?token={token}"


async def issue_decision_token(
    redis: aioredis.Redis,
    *,
    user_id: UUID,
    tenant_id: UUID,
    admin_id: UUID,
    ttl_seconds: int,
) -> str:
    """Token de un solo uso para UN admin concreto: liga qué registro (user_id+tenant_id, F2) y
    quién decide (admin_id, para la auditoría) si se usa este enlace."""
    token = secrets.token_urlsafe(32)
    record = json.dumps(
        {"user_id": str(user_id), "tenant_id": str(tenant_id), "admin_id": str(admin_id)}
    )
    await redis.set(_key(token), record, ex=ttl_seconds)
    return token


async def _load(
    redis: aioredis.Redis,
    session: AsyncSession,
    *,
    token: str,
    expected_tenant_id: UUID,
    settings: Settings,
) -> tuple[dict[str, str], registration_repo.RegistrationSummary]:
    raw = await redis.get(_key(token))
    if raw is None:
        raise InvalidDecisionToken
    data = json.loads(raw)
    if data["tenant_id"] != str(expected_tenant_id):
        raise InvalidDecisionToken
    encryption_key = company_encryption_key(settings, expected_tenant_id)
    summary = await registration_repo.get_registration_summary(
        session, UUID(data["user_id"]), encryption_key=encryption_key
    )
    if summary is None:
        raise InvalidDecisionToken
    return data, summary


async def peek(
    redis: aioredis.Redis,
    session: AsyncSession,
    *,
    token: str,
    expected_tenant_id: UUID,
    settings: Settings,
) -> DecisionSummary:
    """Para la pantalla de confirmación: NO consume el token ni decide nada todavía."""
    _, summary = await _load(
        redis, session, token=token, expected_tenant_id=expected_tenant_id, settings=settings
    )
    return DecisionSummary(
        email=summary.email, company=summary.company, already_decided=summary.status != "pending"
    )


async def decide(
    redis: aioredis.Redis,
    session: AsyncSession,
    *,
    token: str,
    decision: Decision,
    expected_tenant_id: UUID,
    settings: Settings,
) -> DecisionSummary:
    """Aplica la decisión y CONSUME el token, un solo uso incluso si ya estaba decidido.

    Idempotente frente a otros admins: si el registro ya no está `pending` (otro admin decidió,
    por su propio enlace o por el panel, mientras este token seguía vivo), no vuelve a decidir,
    solo informa (`already_decided=True`) -- nunca un error, es una carrera normal entre varios
    admins del mismo tenant, no un fallo.
    """
    # Import perezoso (no a nivel de módulo): `registration.py` importa este módulo para emitir los
    # tokens al registrar, así que un `from identity import registration` arriba crearía un ciclo.
    from identity import registration

    data, summary = await _load(
        redis, session, token=token, expected_tenant_id=expected_tenant_id, settings=settings
    )
    await redis.delete(_key(token))
    if summary.status != "pending":
        return DecisionSummary(email=summary.email, company=summary.company, already_decided=True)
    admin_id = UUID(data["admin_id"])
    if decision == "approve":
        await registration.approve(session, actor_id=admin_id, user_id=summary.id)
    else:
        await registration.reject(session, actor_id=admin_id, user_id=summary.id)
    return DecisionSummary(email=summary.email, company=summary.company, already_decided=False)

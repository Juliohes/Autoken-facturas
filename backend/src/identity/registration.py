"""Casos de uso del registro con aprobación (S1.4): orquestación de dominio, sin HTTP ni SQL.

El router traduce peticiones a estas operaciones y sus excepciones de dominio a códigos HTTP; el SQL
vive en `registration_repo` (usuarios/memberships) y en `companies.repository` (empresas). Aquí solo
las reglas: rate-limit por IP, registro entero o nada, validación de CIF y contraseña, regla 1-A
(una empresa), anti-enumeración del email duplicado (por tiempo y por carrera), aprobación
idempotente y rechazo con limpieza de huérfanos.

Todo corre dentro de la transacción de la sesión abierta por el contexto (registro público o
`tenant_admin`): o entra completo (usuario + empresa + membership + auditoría) o nada. La
notificación al admin se despacha DESPUÉS del commit (post-commit), para no enviar un email por un
registro que no llegó a persistir ni bloquear la transacción con I/O de red.
"""

from __future__ import annotations

from uuid import UUID

import redis.asyncio as aioredis
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from companies import repository as companies_repo
from companies.service import InvalidTaxId, is_cif_unique_violation, validated_cif
from companies.service import cif_blind_index as company_cif_blind_index
from companies.service import tenant_encryption_key as company_encryption_key
from identity import email_verification, ratelimit, registration_repo
from identity.passwords import hash_password, validate_password_policy
from notifications import Message, Notifier
from notifications import templates as email_templates
from shared.audit import write_audit
from shared.config import Settings
from shared.integrity import violates_unique_constraint
from tenancy.constants import CompanyStatus, UserStatus

# Entidad y acciones de auditoría del flujo de registro (append-only, S1.1): en constantes para que
# el registro, la aprobación y el rechazo dejen una traza coherente y no literales sueltos.
_AUDIT_ENTITY = "user"
AUDIT_ACTION_REGISTER = "user.register"
AUDIT_ACTION_APPROVE = "user.approve"
AUDIT_ACTION_REJECT = "user.reject"

# UNIQUE `(tenant_id, email)` de `users` (migración 0001): red última de la unicidad del email. Se
# usa para reabsorber la carrera (TOCTOU) que dos altas concurrentes con el mismo email provocan.
_USERS_EMAIL_UNIQUE = "users_tenant_email_unique"

# Un reintento basta para reabsorber la carrera del UNIQUE de CIF: al reintentar, el SELECT por CIF
# ya encuentra la empresa que creó la otra alta y se vincula a ella (1-A) en vez de duplicarla.
_MAX_PERSIST_ATTEMPTS = 2


class RegistrationError(Exception):
    """Raíz de los errores de dominio del flujo de registro."""


class WeakPassword(RegistrationError):
    """La contraseña no cumple la política (S1.3) (-> 422)."""


class LegalConsentRequired(RegistrationError):
    """El registrante no aceptó los términos/condiciones (Bloque 5, PROMPT-AUTOFACTU-AUTH-COMPLETO)
    (-> 422). Sin esto no hay alta: es el propio consentimiento, no un detalle accesorio."""


class InvalidCif(RegistrationError):
    """El CIF no supera la validación estructural/de dígito de control (-> 422).

    Envuelve `companies.service.InvalidTaxId` para que el router del registro dependa solo de
    excepciones de este módulo, no del contexto `companies`.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class RegistrationRateLimited(RegistrationError):
    """La IP ha superado el tope de altas de la ventana (anti-spam, C14) (-> 429)."""


class RegistrationNotFound(RegistrationError):
    """El registro no existe en el contexto (inexistente u otro tenant) (-> 404)."""


class RegistrationNotPending(RegistrationError):
    """Se intenta rechazar un usuario que ya no está pendiente (ya activo) (-> 409)."""


async def register(
    session: AsyncSession,
    *,
    redis: aioredis.Redis,
    ip: str,
    tenant_id: UUID,
    tenant_slug: str,
    email: str,
    company_name: str,
    cif: str,
    password: str,
    legal_consent: bool,
    settings: Settings,
    notifier: Notifier,
) -> None:
    """Da de alta un registro pendiente: usuario + empresa (1-A) + membership, todo o nada.

    Limita por IP (429), exige el consentimiento legal (422) y valida contraseña (422) y CIF (422)
    antes de tocar nada. La contraseña se
    **hashea siempre** antes de ramificar por la existencia del email, para no filtrar por latencia
    si el email ya existe (mismo criterio que `verify_password` en el login). Si el email ya existe
    no crea un segundo usuario ni avisa: la respuesta la genera el router de forma **genérica e
    idéntica** (anti-enumeración). Deja traza `user.register` (actor = el propio usuario nuevo),
    avisa al `tenant_admin` tras el commit, y (bloque 2) siembra un token de verificación de email y
    avisa TAMBIÉN al propio registrante -- no como aprobación (sigue pendiente del admin), solo para
    confirmar que el email es suyo.
    """
    if await ratelimit.register_attempt_exceeds_ip(
        redis,
        ip,
        max_per_ip=settings.register_max_per_ip,
        window_seconds=settings.register_window_seconds,
    ):
        raise RegistrationRateLimited
    if not legal_consent:
        raise LegalConsentRequired
    if not validate_password_policy(password, settings):
        raise WeakPassword
    canonical_cif = _validated_cif(cif)
    # M1 (anti-enumeración por tiempo): hashear SIEMPRE antes de mirar si el email existe, para que
    # el alta duplicada y la nueva tarden lo mismo (Argon2id no se salta en el camino corto).
    password_hash = hash_password(password)

    if await registration_repo.email_exists(session, email):
        return  # anti-enumeración (fast-path): email ya presente, respuesta genérica sin crear nada

    user_id = await _persist_registration(
        session,
        tenant_id=tenant_id,
        settings=settings,
        email=email,
        company_name=company_name,
        canonical_cif=canonical_cif,
        password_hash=password_hash,
    )
    if user_id is None:
        return  # carrera de email: otra alta ganó el UNIQUE; respuesta genérica, sin crear

    messages = await _admin_messages(
        session, new_email=email, settings=settings, tenant_slug=tenant_slug
    )
    verification_token = await email_verification.issue_verification_token(
        redis,
        user_id=user_id,
        tenant_id=tenant_id,
        ttl_seconds=settings.email_verification_ttl,
    )
    messages.append(
        email_templates.email_verification(
            email=email,
            url=email_verification.verification_url(
                settings, slug=tenant_slug, token=verification_token
            ),
            ttl_seconds=settings.email_verification_ttl,
        )
    )
    _dispatch_after_commit(session, notifier, messages)


def _validated_cif(cif: str) -> str:
    """Forma canónica del CIF o `InvalidCif`; encapsula el `InvalidTaxId` de `companies` (L5)."""
    try:
        return validated_cif(cif)
    except InvalidTaxId as exc:
        raise InvalidCif(exc.reason) from exc


async def _persist_registration(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    settings: Settings,
    email: str,
    company_name: str,
    canonical_cif: str,
    password_hash: str,
) -> UUID | None:
    """Inserta usuario + empresa (1-A) + membership + traza en un SAVEPOINT; el id del usuario si se
    creó, o `None` si no se creó nada.

    El pre-check de unicidad no es atómico: dos altas concurrentes pueden esquivarlo y chocar en un
    UNIQUE. Se capturan esas carreras (TOCTOU):
    - UNIQUE de email -> devuelve `None` (nada creado): el router responde igual que un alta buena.
    - UNIQUE de CIF -> reintenta dentro del SAVEPOINT: al reintentar el SELECT encuentra la empresa
      recién creada por la otra alta y se vincula a ella (1-A), sin duplicarla.
    El SAVEPOINT único evita dejar una empresa huérfana si el alta del usuario falla en la carrera.
    """
    attempts = 0
    while True:
        attempts += 1
        try:
            async with session.begin_nested():
                company_id = await _resolve_company(
                    session,
                    tenant_id=tenant_id,
                    settings=settings,
                    name=company_name,
                    canonical_cif=canonical_cif,
                )
                user_id = await registration_repo.insert_pending_user(
                    session, email=email, password_hash=password_hash
                )
                await registration_repo.insert_membership(
                    session, user_id=user_id, company_id=company_id
                )
                await write_audit(
                    session,
                    actor_id=user_id,
                    action=AUDIT_ACTION_REGISTER,
                    entity=_AUDIT_ENTITY,
                    entity_id=user_id,
                    # `legal_consent` deja constancia verificable (hash) de que el alta se dio con
                    # el consentimiento aceptado (Bloque 5): llegar aquí ya lo exigió `register()`.
                    payload={"legal_consent": True, "email": email, "cif": canonical_cif},
                )
            return user_id
        except IntegrityError as exc:
            if violates_unique_constraint(exc, _USERS_EMAIL_UNIQUE):
                return None  # carrera de email: nada creado, respuesta genérica
            if is_cif_unique_violation(exc) and attempts < _MAX_PERSIST_ATTEMPTS:
                continue  # carrera de CIF: la empresa ya existe; reintenta y vincúlate a ella
            raise  # cualquier otra violación de integridad no se enmascara


async def _resolve_company(
    session: AsyncSession, *, tenant_id: UUID, settings: Settings, name: str, canonical_cif: str
) -> UUID:
    """Regla 1-A: vincula a la empresa existente por CIF o crea una nueva `pending`. Una empresa."""
    encryption_key = company_encryption_key(settings, tenant_id)
    idx = company_cif_blind_index(settings, tenant_id, canonical_cif)
    existing = await companies_repo.get_company_by_cif_blind_index(
        session, idx, encryption_key=encryption_key
    )
    if existing is not None:
        return existing.id
    record = await companies_repo.insert_company(
        session,
        name=name,
        cif=canonical_cif,
        cif_blind_index=idx,
        status=CompanyStatus.PENDING.value,
        notes=None,
        encryption_key=encryption_key,
    )
    return record.id


def _admin_panel_url(settings: Settings, *, slug: str) -> str:
    """Enlace directo a "Empresas -> Registros pendientes de aprobación", en el subdominio del
    propio tenant (nunca cruzado, mismo criterio que `_reset_url`/`verification_url`).

    Hallazgo real (Julio, 2026-09-03): el aviso al admin decía "entra en el panel de tu asesoría
    para revisarlo" sin ningún enlace, así que había que ir a buscar la pantalla a mano.
    """
    return f"https://{slug}.{settings.base_domain}/empresas"


async def _admin_messages(
    session: AsyncSession, *, new_email: str, settings: Settings, tenant_slug: str
) -> list[Message]:
    """Construye el aviso a cada `tenant_admin` activo del registro pendiente (C12).

    En S1.4 original, el usuario final no recibía ningún aviso; el bloque 2
    (PROMPT-AUTOFACTU-AUTH-COMPLETO) añade el aviso de verificación de email al registrante
    (`notifications.templates.email_verification`), que sigue sin ser una notificación de
    aprobación: eso sigue siendo solo cosa del admin. Los destinatarios se leen ahora (dentro del
    contexto RLS de la transacción); el envío se difiere al post-commit.
    """
    panel_url = _admin_panel_url(settings, slug=tenant_slug)
    return [
        email_templates.registration_pending_admin(
            admin_email=admin_email, registrant_email=new_email, panel_url=panel_url
        )
        for admin_email in await registration_repo.tenant_admin_emails(session)
    ]


def _dispatch_after_commit(
    session: AsyncSession, notifier: Notifier, messages: list[Message]
) -> None:
    """Despacha `messages` por el notificador SOLO tras confirmarse el commit (L2, post-commit).

    Usa el evento `after_commit` de SQLAlchemy: si la transacción se revierte, no se envía nada
    (contra el dual-write de "email enviado, registro no persistido"); si commitea, se despacha
    fuera de la transacción, sin bloquearla con I/O de red cuando se cablee el SMTP real.
    """
    if not messages:
        return

    def _send(_sync_session: Session) -> None:
        for message in messages:
            notifier.send(message)

    event.listen(session.sync_session, "after_commit", _send, once=True)


async def list_pending_registrations(
    session: AsyncSession, *, tenant_id: UUID, settings: Settings
) -> list[registration_repo.PendingRegistration]:
    """Lista los registros pendientes de la asesoría (solo lectura): deriva la clave aquí, nunca en
    el router (hallazgo de auditoría S5.2 — la derivación de clave es del servicio, no del router,
    mismo criterio que `companies.service.list_companies`)."""
    encryption_key = company_encryption_key(settings, tenant_id)
    return await registration_repo.list_pending(session, encryption_key=encryption_key)


async def approve(session: AsyncSession, *, actor_id: UUID, user_id: UUID) -> None:
    """Aprueba un registro: activa usuario y su empresa pendiente (3-A). Idempotente si ya activo.

    Fuera del contexto (inexistente u otro tenant) -> `RegistrationNotFound` (404, RLS). Aprobar un
    usuario ya activo es un no-op (no reactiva ni duplica traza).
    """
    user = await registration_repo.get_user(session, user_id)
    if user is None:
        raise RegistrationNotFound
    if user.status == UserStatus.ACTIVE:
        return  # idempotente: ya aprobado, nada que hacer
    for company in await registration_repo.linked_companies(session, user_id):
        # La activación la hace el propio contexto `companies` (simetría de escritura), que solo
        # toca las `pending` (una empresa ya activa, vínculo 1-A, se deja igual).
        await companies_repo.activate_pending_company(session, company.id)
    await registration_repo.activate_user(session, user_id)
    await write_audit(
        session,
        actor_id=actor_id,
        action=AUDIT_ACTION_APPROVE,
        entity=_AUDIT_ENTITY,
        entity_id=user_id,
    )


async def reject(session: AsyncSession, *, actor_id: UUID, user_id: UUID) -> None:
    """Rechaza un registro pendiente: borra el usuario y su empresa si queda huérfana (C9).

    Conserva la empresa si tiene otros miembros o si no la creó este registro (estaba ya activa).
    Fuera del contexto -> 404; un usuario ya activo no es un registro pendiente (409,
    `RegistrationNotPending`).
    """
    user = await registration_repo.get_user(session, user_id)
    if user is None:
        raise RegistrationNotFound
    if user.status == UserStatus.ACTIVE:
        raise RegistrationNotPending

    # Se capturan las empresas ANTES de borrar (las memberships caen en cascada con el usuario).
    linked = await registration_repo.linked_companies(session, user_id)
    await registration_repo.delete_user(session, user_id)
    for company in linked:
        # Solo se borra la empresa creada por este registro (pendiente) y sin otros miembros: una
        # empresa ya activa (vínculo 1-A a una existente) o con más miembros se conserva.
        if (
            company.status == CompanyStatus.PENDING
            and await companies_repo.count_memberships(session, company.id) == 0
        ):
            await companies_repo.delete_company(session, company.id)
    await write_audit(
        session,
        actor_id=actor_id,
        action=AUDIT_ACTION_REJECT,
        entity=_AUDIT_ENTITY,
        entity_id=user_id,
    )

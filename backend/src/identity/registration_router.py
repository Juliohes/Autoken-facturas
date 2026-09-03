"""Endpoints HTTP del registro con aprobación (S1.4): alta pública + gestión del `tenant_admin`.

Capa HTTP **fina**: traduce la petición a un caso de uso (`identity.registration`) y su resultado o
excepción de dominio a la respuesta. Sin SQL ni reglas de negocio (ni siquiera el rate-limit del
alta, ni la derivación de la clave de cifrado del listado, S5.2 — ambos viven en el caso de uso,
autocontenido).

`POST /register` es **público** en el subdominio: no pasa por `require_roles` (no hay token), abre
el contexto del tenant desde el host (`public_tenant_context`) y se limita por IP (anti-spam). La
gestión (`GET /registrations`, `approve`, `reject`) es solo `tenant_admin` (portero de S1.6),
acotada al tenant por RLS.

`GET/POST /auth/registrations/decision` son TAMBIÉN públicos (2026-09-03): la puerta no es un
`require_roles`, es el propio token de un solo uso del email de aviso (`identity.
registration_decision`), ligado a qué admin decide para que la auditoría siga siendo correcta.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from identity import registration, registration_decision
from identity.authz import require_roles
from identity.client_ip import client_ip
from identity.dependencies import AuthContext
from notifications import Notifier, get_notifier
from shared.config import get_settings
from shared.redis import RedisError, get_redis
from tenancy.constants import Role
from tenancy.context import PublicTenantContext, public_tenant_context

router = APIRouter(tags=["registration"])

# Dependencia común de la gestión: identidad autenticada y autorizada como `tenant_admin` (S1.6).
TenantAdmin = Annotated[AuthContext, Depends(require_roles(Role.TENANT_ADMIN))]
# Contexto del tenant del subdominio, sin token, para el registro público.
PublicContext = Annotated[PublicTenantContext, Depends(public_tenant_context)]
# Notificador del proceso, inyectado (DIP): el caso de uso no alcanza el singleton global.
NotifierDep = Annotated[Notifier, Depends(get_notifier)]


class RegisterRequest(BaseModel):
    """Cuerpo de `POST /register`."""

    email: str
    company_name: str
    cif: str
    password: str
    legal_consent: bool


class RegisterResponse(BaseModel):
    """Respuesta genérica del registro (idéntica exista o no el email: anti-enumeración)."""

    status: str


class RegistrationOut(BaseModel):
    """Un registro pendiente en el listado del admin (email + empresa + señal de unión a existente).

    `joins_existing_company` avisa a la pantalla de aprobación de que el CIF casaba con una empresa
    ya activa (el usuario se une a ella, no crea empresa nueva): defensa ante secuestro por CIF.
    """

    id: UUID
    email: str
    company: str | None
    joins_existing_company: bool


class ApprovalResponse(BaseModel):
    """Respuesta de la aprobación de un registro."""

    status: str


class DecisionInfoOut(BaseModel):
    """Lo que ve la pantalla de decisión por email antes de que el admin elija (`GET
    /auth/registrations/decision`): nunca muta nada, solo informa."""

    email: str
    company: str | None
    already_decided: bool


class DecideRequest(BaseModel):
    """Cuerpo de `POST /auth/registrations/decision`: la única llamada que de verdad aprueba o
    rechaza (F5, ver `identity.registration_decision`)."""

    token: str
    decision: Literal["approve", "reject"]


class DecideResponse(BaseModel):
    """Respuesta de la decisión por email."""

    status: Literal["approved", "rejected", "already_decided"]


@router.post("/register", status_code=201)
async def register(
    request: Request, body: RegisterRequest, context: PublicContext, notifier: NotifierDep
) -> RegisterResponse:
    """Alta autoservicio en el subdominio. CIF/contraseña inválidos -> 422; tope por IP -> 429.

    Respuesta **genérica e idéntica** exista o no ya el email (anti-enumeración): un email duplicado
    no crea nada pero responde igual que un alta correcta.
    """
    settings = get_settings()
    ip = client_ip(request, settings)
    try:
        await registration.register(
            context.session,
            redis=get_redis(),
            ip=ip,
            tenant_id=context.tenant.id,
            tenant_slug=context.tenant.slug,
            email=body.email,
            company_name=body.company_name,
            cif=body.cif,
            password=body.password,
            legal_consent=body.legal_consent,
            settings=settings,
            notifier=notifier,
        )
    except RedisError as exc:
        # Sin Redis no se puede aplicar el anti-spam: la petición falla cerrada (503), no "pasa
        # todo el mundo".
        raise HTTPException(status_code=503, detail="Service unavailable") from exc
    except registration.RegistrationRateLimited as exc:
        raise HTTPException(status_code=429, detail="Too many registrations") from exc
    except registration.LegalConsentRequired as exc:
        raise HTTPException(status_code=422, detail="legal consent is required") from exc
    except registration.WeakPassword as exc:
        raise HTTPException(status_code=422, detail="password does not meet policy") from exc
    except registration.InvalidCif as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    return RegisterResponse(status="pending_approval")


@router.get("/registrations")
async def list_registrations(identity: TenantAdmin) -> list[RegistrationOut]:
    """Lista los registros pendientes de la asesoría (solo `tenant_admin`; la RLS acota)."""
    rows = await registration.list_pending_registrations(
        identity.session, tenant_id=identity.tenant_id, settings=get_settings()
    )
    return [
        RegistrationOut(
            id=r.id,
            email=r.email,
            company=r.company,
            joins_existing_company=r.joins_existing_company,
        )
        for r in rows
    ]


@router.get("/auth/registrations/decision")
async def registration_decision_info(token: str, context: PublicContext) -> DecisionInfoOut:
    """Lo que muestra la pantalla de decisión por email antes de elegir. Nunca muta nada (F5): un
    escáner de enlaces de email que precargue esta URL no aprueba ni rechaza nada."""
    settings = get_settings()
    try:
        summary = await registration_decision.peek(
            get_redis(),
            context.session,
            token=token,
            expected_tenant_id=context.tenant.id,
            settings=settings,
        )
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Service unavailable") from exc
    except registration_decision.InvalidDecisionToken as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    return DecisionInfoOut(
        email=summary.email, company=summary.company, already_decided=summary.already_decided
    )


@router.post("/auth/registrations/decision")
async def registration_decide(body: DecideRequest, context: PublicContext) -> DecideResponse:
    """Aprueba o rechaza un registro desde el enlace de un solo uso del email (2026-09-03, a
    petición de Julio): sin token de sesión, sin panel, la única llamada que de verdad decide."""
    settings = get_settings()
    try:
        summary = await registration_decision.decide(
            get_redis(),
            context.session,
            token=body.token,
            decision=body.decision,
            expected_tenant_id=context.tenant.id,
            settings=settings,
        )
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Service unavailable") from exc
    except registration_decision.InvalidDecisionToken as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    if summary.already_decided:
        return DecideResponse(status="already_decided")
    return DecideResponse(status="approved" if body.decision == "approve" else "rejected")


@router.post("/registrations/{user_id}/approve")
async def approve_registration(identity: TenantAdmin, user_id: UUID) -> ApprovalResponse:
    """Aprueba un registro: activa usuario + empresa. Idempotente; de otro tenant -> 404."""
    try:
        await registration.approve(identity.session, actor_id=identity.user_id, user_id=user_id)
    except registration.RegistrationNotFound as exc:
        raise HTTPException(status_code=404, detail="Registro no encontrado") from exc
    return ApprovalResponse(status="active")


@router.post("/registrations/{user_id}/reject", status_code=204)
async def reject_registration(identity: TenantAdmin, user_id: UUID) -> Response:
    """Rechaza un registro pendiente: borra el usuario y su empresa huérfana. Otro tenant -> 404."""
    try:
        await registration.reject(identity.session, actor_id=identity.user_id, user_id=user_id)
    except registration.RegistrationNotFound as exc:
        raise HTTPException(status_code=404, detail="Registro no encontrado") from exc
    except registration.RegistrationNotPending as exc:
        raise HTTPException(status_code=409, detail="El registro ya no está pendiente") from exc
    return Response(status_code=204)

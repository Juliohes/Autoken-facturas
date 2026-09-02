"""Endpoints HTTP de recuperación de contraseña (PROMPT-AUTOFACTU-AUTH-COMPLETO, bloque 1).

Capa HTTP fina: traduce la petición a `identity.password_reset` y sus excepciones de dominio a la
respuesta. Los dos endpoints son públicos en el subdominio (sin token): abren el contexto del
tenant desde el host, igual que `POST /register` (`identity.registration_router`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from identity import password_reset
from identity.client_ip import client_ip
from notifications import Notifier, get_notifier
from shared.config import get_settings
from shared.redis import RedisError, get_redis
from tenancy.context import PublicTenantContext, public_tenant_context

router = APIRouter(prefix="/auth/password", tags=["auth"])

PublicContext = Annotated[PublicTenantContext, Depends(public_tenant_context)]
NotifierDep = Annotated[Notifier, Depends(get_notifier)]


class ForgotPasswordRequest(BaseModel):
    """Cuerpo de `POST /auth/password/forgot`."""

    email: str


class ForgotPasswordResponse(BaseModel):
    """Respuesta genérica del olvido de contraseña (idéntica exista o no la cuenta:
    anti-enumeración)."""

    status: str


class ResetPasswordRequest(BaseModel):
    """Cuerpo de `POST /auth/password/reset`."""

    token: str
    password: str


class ResetPasswordResponse(BaseModel):
    """Respuesta del restablecimiento efectivo."""

    status: str


@router.post("/forgot")
async def forgot_password(
    request: Request, body: ForgotPasswordRequest, context: PublicContext, notifier: NotifierDep
) -> ForgotPasswordResponse:
    """Solicita un enlace de restablecimiento. Respuesta genérica: 200 exista o no la cuenta.

    Tope por (IP+email) e IP -> 429. Sin Redis no se puede aplicar el anti-spam ni sembrar el
    token: la petición falla cerrada (503).
    """
    settings = get_settings()
    ip = client_ip(request, settings)
    try:
        await password_reset.request_reset(
            context.session,
            redis=get_redis(),
            ip=ip,
            tenant_id=context.tenant.id,
            tenant_slug=context.tenant.slug,
            email=body.email,
            settings=settings,
            notifier=notifier,
        )
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Service unavailable") from exc
    except password_reset.PasswordResetRateLimited as exc:
        raise HTTPException(status_code=429, detail="Too many attempts") from exc
    return ForgotPasswordResponse(status="if_exists_sent")


@router.post("/reset")
async def reset_password(
    body: ResetPasswordRequest, context: PublicContext
) -> ResetPasswordResponse:
    """Fija la nueva contraseña con un token de restablecimiento válido y cierra otras sesiones.

    Token inválido/caducado/consumido, o de otro tenant (F2) -> 401 (no distingue el motivo).
    Contraseña débil -> 422.
    """
    settings = get_settings()
    try:
        await password_reset.reset_password(
            get_redis(),
            context.session,
            token=body.token,
            password=body.password,
            expected_tenant_id=context.tenant.id,
            settings=settings,
        )
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Service unavailable") from exc
    except password_reset.InvalidResetToken as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    except password_reset.WeakPassword as exc:
        raise HTTPException(status_code=422, detail="password does not meet policy") from exc
    return ResetPasswordResponse(status="reset")

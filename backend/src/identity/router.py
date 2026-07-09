"""Endpoints de autenticación (S1.3): login, refresh, logout, activación y el testigo `/auth/me`.

Capa **HTTP fina**: traduce peticiones a casos de uso (`identity.service`) y accesos a datos
(`identity.repository`), y sus resultados a respuestas. No contiene SQL, ni orquestación de dominio,
ni la validación de negocio (viven en `service`/`repository`/`passwords`).

Transporte de la sesión (ADR-0012): el access token viaja en el cuerpo (el frontend lo guarda en
memoria y lo manda por `Authorization: Bearer`); el refresh viaja en una cookie `httpOnly, Secure,
SameSite=Strict` acotada a las rutas de auth (no visible a JavaScript).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, assert_never

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from identity import activation, repository, service, sessions
from identity.dependencies import AuthContext, current_identity
from identity.passwords import validate_password_policy
from identity.tokens import encode_access_token
from shared.config import Settings, get_settings
from shared.redis import RedisError, get_redis
from tenancy.resolution import ResolvedTenant

router = APIRouter(prefix="/auth", tags=["auth"])

_REFRESH_COOKIE = "refresh_token"
_COOKIE_PATH = "/api/v1/auth"
# Respuesta 401 neutra de login: idéntica para credenciales malas, email inexistente y cuenta no
# activa (anti-enumeración, §4). No revela cuál de los tres motivos ha fallado.
_NEUTRAL_401 = "Invalid credentials"


class LoginRequest(BaseModel):
    """Cuerpo de `POST /auth/login`."""

    email: str
    password: str
    totp_code: str | None = None


class ActivateRequest(BaseModel):
    """Cuerpo de `POST /auth/activate`. La política de contraseña la valida el endpoint."""

    token: str
    password: str


class ActivateConfirmRequest(BaseModel):
    """Cuerpo de `POST /auth/activate/confirm`."""

    token: str
    totp_code: str


@contextmanager
def _redis_guard() -> Iterator[None]:
    """Traduce `RedisError` a 503 (fallo cerrado, §5) en un solo sitio, en vez de repetir el except.

    Sin Redis no se puede comprobar el rate-limit, rotar el refresh ni gobernar la activación: la
    petición falla cerrada (503), nunca "pasa todo el mundo".
    """
    try:
        yield
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Service unavailable") from exc


def _client_ip(request: Request, settings: Settings) -> str:
    """IP real del cliente para el rate-limit (C17/C22), a prueba de proxy inverso (B1).

    `request.client.host` es la IP del **peer directo**: tras Traefik/Caddy sería la del proxy, la
    misma para todos (un fallo de cualquiera bloquearía a toda la plataforma). Se deriva la IP real
    de `X-Forwarded-For` SOLO si la petición viene de un proxy de confianza (`trusted_proxies`);
    nunca se confía en XFF crudo de una fuente no confiable (evita spoofing del rate-limit).
    """
    peer = request.client.host if request.client is not None else "unknown"
    trusted = settings.trusted_proxy_set
    if not trusted:
        return peer  # sin proxies de confianza configurados: la IP es la del peer directo
    trust_all = "*" in trusted
    if not trust_all and peer not in trusted:
        return peer  # la petición no viene de un proxy de confianza: se ignora XFF
    forwarded = [
        p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()
    ]
    if not forwarded:
        return peer
    if trust_all:
        return forwarded[0]  # se confía en toda la cadena: el cliente original es el primero
    for candidate in reversed(forwarded):
        if candidate not in trusted:
            return candidate  # primer salto no-confiable desde la derecha = cliente real
    return forwarded[0]


def _set_refresh_cookie(response: JSONResponse, token: str, settings: Settings) -> None:
    response.set_cookie(
        _REFRESH_COOKIE,
        token,
        max_age=settings.jwt_refresh_ttl,
        httponly=True,
        secure=True,
        samesite="strict",
        path=_COOKIE_PATH,
    )


def _session_response(
    *,
    user_id: str,
    tenant_id: str | None,
    role: str,
    refresh_token: str,
    settings: Settings,
) -> JSONResponse:
    """Respuesta de sesión: access token en el cuerpo + Set-Cookie del refresh (login y refresh)."""
    access = encode_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        secret=settings.jwt_secret,
        ttl_seconds=settings.jwt_access_ttl,
    )
    response = JSONResponse(content={"access_token": access, "token_type": "bearer"})
    _set_refresh_cookie(response, refresh_token, settings)
    return response


@router.post("/login")
async def login(request: Request, body: LoginRequest) -> JSONResponse:
    """Autentica email + contraseña (+ TOTP si aplica): access token + cookie de refresh."""
    settings = get_settings()
    resolved: ResolvedTenant | None = getattr(request.state, "tenant", None)
    platform_login: bool = getattr(request.state, "is_platform_host", False)
    ip = _client_ip(request, settings)
    with _redis_guard():
        result = await service.authenticate(
            get_redis(),
            resolved=resolved,
            platform_login=platform_login,
            ip=ip,
            email=body.email,
            password=body.password,
            totp_code=body.totp_code,
            settings=settings,
        )
    match result:
        case service.LoginSucceeded() as ok:
            return _session_response(
                user_id=ok.user_id,
                tenant_id=ok.tenant_id,
                role=ok.role,
                refresh_token=ok.refresh_token,
                settings=settings,
            )
        case service.TotpRequired():
            return JSONResponse(status_code=401, content={"totp_required": True})
        case service.RateLimited():
            raise HTTPException(status_code=429, detail="Too many attempts")
        case service.NeutralFailure():
            raise HTTPException(status_code=401, detail=_NEUTRAL_401)
        case _:
            assert_never(result)


@router.post("/refresh")
async def refresh(request: Request) -> JSONResponse:
    """Rota el refresh de la cookie: nuevo access + nueva cookie; el anterior queda invalidado."""
    settings = get_settings()
    token = request.cookies.get(_REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Defensa en profundidad (F2): el subdominio por el que llega debe casar con el tenant de la
    # familia del refresh; si no, no se rota (coherente con "el subdominio aísla").
    resolved: ResolvedTenant | None = getattr(request.state, "tenant", None)
    expected_tenant = str(resolved.id) if resolved is not None else None
    with _redis_guard():
        rotated = await sessions.rotate_refresh_token(
            get_redis(),
            token,
            expected_tenant_id=expected_tenant,
            ttl_seconds=settings.jwt_refresh_ttl,
        )
    if rotated is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    return _session_response(
        user_id=rotated.user_id,
        tenant_id=rotated.tenant_id,
        role=rotated.role,
        refresh_token=rotated.new_token,
        settings=settings,
    )


@router.post("/logout")
async def logout(request: Request) -> JSONResponse:
    """Revoca la familia del refresh y borra la cookie. Idempotente sin cookie."""
    settings = get_settings()
    token = request.cookies.get(_REFRESH_COOKIE)
    if token:
        with _redis_guard():
            await sessions.revoke_family(get_redis(), token, ttl_seconds=settings.jwt_refresh_ttl)
    response = JSONResponse(content={"status": "logged_out"})
    response.delete_cookie(_REFRESH_COOKIE, path=_COOKIE_PATH)
    return response


@router.post("/activate")
async def activate(body: ActivateRequest) -> dict[str, str]:
    """Fija la contraseña y genera el secreto TOTP; devuelve la URI `otpauth://` para el QR."""
    settings = get_settings()
    if not validate_password_policy(body.password, settings):
        raise HTTPException(status_code=422, detail="password does not meet policy")
    with _redis_guard():
        try:
            otpauth_uri = await activation.activate_account(
                get_redis(), body.token, body.password, ttl_seconds=settings.activation_ttl
            )
        except (activation.InvalidActivationToken, activation.AccountNotActivatable) as exc:
            raise HTTPException(status_code=401, detail="Invalid activation token") from exc
    return {"otpauth_uri": otpauth_uri}


@router.post("/activate/confirm")
async def activate_confirm(body: ActivateConfirmRequest) -> dict[str, str]:
    """Confirma el TOTP: enrola el segundo factor y consume el token de activación (un solo uso)."""
    with _redis_guard():
        try:
            await activation.confirm_activation(get_redis(), body.token, body.totp_code)
        except activation.InvalidActivationToken as exc:
            raise HTTPException(status_code=401, detail="Invalid activation token") from exc
    return {"status": "active"}


@router.get("/me")
async def me(identity: Annotated[AuthContext, Depends(current_identity)]) -> dict[str, object]:
    """Testigo protegido: la identidad del token, leída bajo el contexto del tenant (RLS).

    Incluye `company` (id y nombre) para un `user` acotado a su empresa; `null` para un
    `tenant_admin` (contexto de asesoría, ve todo el tenant). Ver spec S1.6 (C5/C6).
    """
    row = await repository.read_identity(identity.session, str(identity.user_id))
    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    company = (
        {"id": str(identity.company.id), "name": identity.company.name}
        if identity.company is not None
        else None
    )
    return {
        "id": row.id,
        "email": row.email,
        "role": row.role,
        "tenant": identity.tenant_slug,
        "company": company,
    }

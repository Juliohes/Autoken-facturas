"""Access token JWT (HS256, vida corta) — S1.3, ADR-0012.

El access token prueba la identidad en cada petición: lleva `sub` (id de usuario), `tenant_id`,
`role` y `exp` corto, firmado con `JWT_SECRET` (HS256). Viaja en la cabecera `Authorization: Bearer`
(lo guarda el frontend en memoria). El refresh, de vida larga, va aparte (ver `identity.sessions`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import jwt

_ALGORITHM = "HS256"


class InvalidAccessToken(Exception):
    """El access token no es válido (firma, expiración, formato o tipo incorrectos)."""


@dataclass(frozen=True)
class AccessClaims:
    """Claims tipadas de un access token válido: el borde del módulo no cruza dicts crudos."""

    sub: str
    tenant_id: str | None
    role: str


def encode_access_token(
    *,
    user_id: str,
    tenant_id: str | None,
    role: str,
    secret: str,
    ttl_seconds: int,
) -> str:
    """Firma un access token con las claims mínimas y un `exp` a `ttl_seconds` del momento."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_access_token(token: str, *, secret: str) -> AccessClaims:
    """Valida firma/exp y devuelve las claims tipadas. Lanza `InvalidAccessToken` si no vale."""
    try:
        # Algoritmo FIJADO a HS256 (nunca se acepta `alg` del token, ni `none`); `exp` y `sub`
        # obligatorios (un token sin expiración o sin sujeto se rechaza, defensa en profundidad).
        claims: dict[str, Any] = jwt.decode(
            token,
            secret,
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidAccessToken(str(exc)) from exc
    if claims.get("type") != "access":
        raise InvalidAccessToken("tipo de token inesperado")
    sub, role = claims.get("sub"), claims.get("role")
    if not isinstance(sub, str) or not isinstance(role, str):
        raise InvalidAccessToken("faltan claims obligatorias (sub/role)")
    tenant_id = claims.get("tenant_id")
    if tenant_id is not None and not isinstance(tenant_id, str):
        raise InvalidAccessToken("tenant_id con tipo inesperado")
    return AccessClaims(sub=sub, tenant_id=tenant_id, role=role)

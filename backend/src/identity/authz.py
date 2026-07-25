"""Portero de roles (RBAC): autoriza una petición ya autenticada según su rol (S1.6).

`require_roles(*roles)` construye una dependencia sobre `current_identity` (S1.3): si la identidad
no está entre los roles permitidos del endpoint, responde **403**. El **401** (no autenticado) lo da
`current_identity` antes, así que la autenticación siempre se comprueba antes que la autorización
(prioridad 401 sobre 403, spec S1.6 C3). Denegar por defecto: una ruta de negocio sin este portero
no debería quedar accesible por olvido (spec S1.6 C10).
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from fastapi.dependencies.models import Dependant

from identity.dependencies import (
    AdminTechAuthContext,
    AuthContext,
    PlatformAuthContext,
    current_admin_tech_identity,
    current_identity,
    current_identity_for_me,
    current_platform_identity,
)
from tenancy.constants import Role

# Atributo con el que se marca la dependencia `guard` que produce `require_roles`, para que el guard
# anti-olvido C10 (`declared_roles`) reconozca por inspección qué rutas declaran roles y detecte las
# que quedaron sin proteger (spec S1.6 C10).
ROLES_MARKER = "__rbac_required_roles__"


def require_roles(*roles: Role) -> Callable[..., Coroutine[Any, Any, AuthContext]]:
    """Devuelve una dependencia que exige que el rol de la identidad esté entre `roles` (o 403)."""
    allowed = frozenset(str(role) for role in roles)

    async def guard(
        identity: Annotated[AuthContext, Depends(current_identity)],
    ) -> AuthContext:
        if identity.role not in allowed:
            raise HTTPException(status_code=403, detail="Forbidden")
        return identity

    setattr(guard, ROLES_MARKER, allowed)
    return guard


def require_platform_admin() -> Callable[..., Coroutine[Any, Any, PlatformAuthContext]]:
    """Dependencia que exige un `platform_admin` ya autenticado (S4.1), sin contexto de tenant.

    `current_platform_identity` ya solo deja pasar `platform_admin` (403 para cualquier otro rol);
    este wrapper no añade ninguna comprobación, solo lleva el mismo `ROLES_MARKER` que
    `require_roles` para que el guard anti-olvido C10 reconozca la ruta como protegida por rol,
    aunque no pase por `current_identity` (un `platform_admin` no tiene tenant que resolver).
    """
    allowed = frozenset({str(Role.PLATFORM_ADMIN)})

    async def guard(
        identity: Annotated[PlatformAuthContext, Depends(current_platform_identity)],
    ) -> PlatformAuthContext:
        return identity

    setattr(guard, ROLES_MARKER, allowed)
    return guard


def require_admin_tech() -> Callable[..., Coroutine[Any, Any, AdminTechAuthContext]]:
    """Dependencia que exige un `platform_admin` con el flag `is_admin_tech` activo (S4.10).

    Chequeo puro sobre un campo ya resuelto (`AdminTechAuthContext.is_admin_tech`), igual que
    `require_roles`/`require_platform_admin`: la resolución fresca contra BD del flag (es un ajuste
    revocable directamente en Postgres, spec §0 decisión 2, que debe dejar de funcionar al instante
    sin esperar a que caduque el token) vive en `current_admin_tech_identity`
    (`identity/dependencies.py`), no aquí — `authz.py` decide según datos ya cargados, nunca los
    carga él mismo.
    """
    allowed = frozenset({str(Role.PLATFORM_ADMIN)})

    async def guard(
        identity: Annotated[AdminTechAuthContext, Depends(current_admin_tech_identity)],
    ) -> AdminTechAuthContext:
        if not identity.is_admin_tech:
            raise HTTPException(status_code=403, detail="Forbidden")
        return identity

    setattr(guard, ROLES_MARKER, allowed)
    return guard


def declared_roles(dependant: Dependant) -> frozenset[str] | None:
    """Roles que `require_roles` declara en el árbol de dependencias de la ruta (`None` si no hay).

    Recorre `route.dependant` (paths + sub-dependencias) buscando la marca `ROLES_MARKER` que deja
    `require_roles` sobre su `guard`. `None` significa que la ruta **no** pasa por el portero de
    roles (candidata a olvido salvo que esté en la allowlist explícita del guard C10).
    """
    call = getattr(dependant, "call", None)
    roles: frozenset[str] | None = getattr(call, ROLES_MARKER, None)
    if roles is not None:
        return roles
    for sub in dependant.dependencies:
        found = declared_roles(sub)
        if found is not None:
            return found
    return None


def requires_authentication(dependant: Dependant) -> bool:
    """True si la ruta autentica (pasa por `current_identity`/`current_identity_for_me`) en algún
    punto de su árbol.

    Sirve al guard C10 para verificar que una ruta abierta a propósito (p. ej. `/auth/me`, sin
    roles) siga exigiendo identidad, aunque no restrinja por rol. `current_identity_for_me` (hotfix
    S4.10) es la variante que además admite a un `platform_admin`; cuenta igual porque decodifica y
    valida el token en todos sus caminos (401 sin uno válido), igual que `current_identity`.
    """
    if getattr(dependant, "call", None) in (current_identity, current_identity_for_me):
        return True
    return any(requires_authentication(sub) for sub in dependant.dependencies)

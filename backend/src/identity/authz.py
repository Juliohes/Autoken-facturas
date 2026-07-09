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

from identity.dependencies import AuthContext, current_identity
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
    """True si la ruta autentica (pasa por `current_identity`) en algún punto de su árbol.

    Sirve al guard C10 para verificar que una ruta abierta a propósito (p. ej. `/auth/me`, sin
    roles) siga exigiendo identidad, aunque no restrinja por rol.
    """
    if getattr(dependant, "call", None) is current_identity:
        return True
    return any(requires_authentication(sub) for sub in dependant.dependencies)

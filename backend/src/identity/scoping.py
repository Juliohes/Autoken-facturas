"""Decisión de contexto RLS según el rol (allowlist explícita, denegar por defecto) — S1.6.

`current_identity` (`identity.dependencies`) usa esta pieza para fijar el nivel de empresa de la RLS
según el rol de la identidad ya validada. Es una **allowlist**: solo los roles contemplados obtienen
un contexto; cualquier otro rol se **deniega** (`RoleNotAuthorized` -> 403), nunca se concede
visibilidad amplia por defecto (ADR-0013, auditoría S1.6 A2).

Vive en su propio módulo (no en `authz.py`) para no crear un ciclo de imports: `authz.require_roles`
depende de `dependencies.current_identity`, que a su vez usa esta decisión.
"""

from __future__ import annotations

from enum import Enum, auto

from tenancy.constants import Role


class RoleNotAuthorized(Exception):
    """El rol de la identidad no está en la allowlist de contextos: se deniega (403)."""


class RlsScope(Enum):
    """Nivel de la RLS que abre la petición según el rol."""

    COMPANY = auto()  # `user`: acotado a su única empresa activa (`app.company_id`)
    TENANT = auto()  # `tenant_admin`: contexto de asesoría (sin `company_id`, ve todo el tenant)


def scope_for_role(role: str) -> RlsScope:
    """Mapea el rol a su contexto RLS por allowlist explícita.

    - `user` -> `COMPANY` (contexto de empresa).
    - `tenant_admin` -> `TENANT` (contexto de asesoría).
    - cualquier otro rol -> `RoleNotAuthorized` (403): nunca se concede un contexto amplio por
      defecto a un rol no contemplado (denegar por defecto).
    """
    if role == Role.USER:
        return RlsScope.COMPANY
    if role == Role.TENANT_ADMIN:
        return RlsScope.TENANT
    raise RoleNotAuthorized(role)

"""Resolución subdominio -> tenant (S1.2).

Dos piezas puras + una de acceso a datos:
- `extract_subdomain`: del `Host` saca el slug de primer nivel (o `None` si es dominio raíz,
  reservado de plataforma, o un host que no cuelga del dominio base).
- `resolve_tenant`: llama a la función SQL acotada `resolve_tenant(slug)` (SECURITY DEFINER) por el
  único camino permitido, sin abrir lectura directa de `tenants`.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from shared.db import session

# Subdominios que NO son asesorías (plataforma / alias del dominio raíz). No resuelven a tenant.
_RESERVED = frozenset({"www", "panel", "panel-staging"})
# Dominios base admitidos para extraer el subdominio (producción + conveniencia de desarrollo).
_DEV_BASE = "localhost"


@dataclass(frozen=True)
class ResolvedTenant:
    """Datos PÚBLICOS de un tenant resueltos por slug (nunca secretos)."""

    id: UUID
    slug: str
    name: str
    is_demo: bool


def extract_subdomain(host: str, base_domain: str, *, allow_localhost: bool = True) -> str | None:
    """Slug de primer nivel de `host`, o `None` si es raíz, reservado o ajeno al dominio base.

    Ignora puerto, caja y el punto final del FQDN. `ilex.autoken.es` -> `ilex`;
    `autoken.es`/`www.autoken.es` -> None; `panel.autoken.es` -> None; una IP o un host que no
    cuelga del dominio base -> None. `localhost` solo se admite como base en desarrollo
    (`allow_localhost`), nunca en producción (evita spoofing de `*.localhost` por cabecera Host).
    """
    hostname = host.split(":", 1)[0].strip().rstrip(".").lower()
    if not hostname:
        return None
    bases = [base_domain.lower()]
    if allow_localhost:
        bases.append(_DEV_BASE)
    for base in bases:
        if hostname == base:
            return None  # dominio raíz: web corporativa, no tenant
        suffix = f".{base}"
        if hostname.endswith(suffix):
            label = hostname[: -len(suffix)].split(".")[0]  # primer nivel
            if label and label not in _RESERVED:
                return label
            return None
    return None  # no cuelga de un dominio base conocido (custom_domain fuera de alcance)


async def resolve_tenant(slug: str) -> ResolvedTenant | None:
    """Resuelve un slug a su tenant activo vía la función SQL acotada (o `None` si no existe)."""
    async with session() as db_session:
        row = (
            await db_session.execute(
                text("SELECT id, slug, name, is_demo FROM resolve_tenant(:slug)"),
                {"slug": slug},
            )
        ).first()
    if row is None:
        return None
    return ResolvedTenant(id=row.id, slug=row.slug, name=row.name, is_demo=row.is_demo)

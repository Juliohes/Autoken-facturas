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
from tenancy.constants import PLATFORM_SUBDOMAINS, RESERVED_SLUGS

# Dominios base admitidos para extraer el subdominio (producción + conveniencia de desarrollo).
_DEV_BASE = "localhost"


@dataclass(frozen=True)
class ResolvedTenant:
    """Datos PÚBLICOS de un tenant resueltos por slug (nunca secretos)."""

    id: UUID
    slug: str
    name: str
    is_demo: bool


def _first_label(host: str, base_domain: str, *, allow_localhost: bool) -> str | None:
    """Única etiqueta de primer nivel de `host` bajo un dominio base (sin filtrar reservados).

    Ignora puerto, caja y el punto final del FQDN. `ilex.autoken.es` -> `ilex`;
    `panel.autoken.es` -> `panel`; el dominio raíz, una IP o un host ajeno al dominio base -> None.
    `localhost` solo se admite como base en desarrollo (evita spoofing de `*.localhost` por Host).

    Endurecimiento (auditoría S1.6 A1, defensa en profundidad): el prefijo bajo el dominio base
    debe tener **exactamente una** etiqueta. Un prefijo multi-etiqueta (contiene un punto, p. ej.
    `panel.foo.autoken.es` o `ilex.x.autoken.es`) se **rechaza** (None), en vez de colapsarlo a su
    primera etiqueta: así un `Host` manipulado no puede hacerse pasar por el panel de plataforma ni
    por un subdominio de tenant. No se confía en que el proxy inverso sanee `Host`.
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
            prefix = hostname[: -len(suffix)]
            # Un prefijo vacío o multi-etiqueta (con punto) no es un subdominio de primer nivel
            # legítimo: se rechaza (no se colapsa a la primera etiqueta).
            if not prefix or "." in prefix:
                return None
            return prefix
    return None  # no cuelga de un dominio base conocido (custom_domain fuera de alcance)


def extract_subdomain(host: str, base_domain: str, *, allow_localhost: bool = True) -> str | None:
    """Slug de asesoría de `host`, o `None` si es raíz, reservado (plataforma) o ajeno al base.

    `ilex.autoken.es` -> `ilex`; `autoken.es`/`www.autoken.es` -> None; `panel.autoken.es` -> None.
    """
    label = _first_label(host, base_domain, allow_localhost=allow_localhost)
    if label is None or label in RESERVED_SLUGS:
        return None
    return label


def is_platform_host(host: str, base_domain: str, *, allow_localhost: bool = True) -> bool:
    """True si `host` es el panel de plataforma (`panel`/`panel-staging`).

    Es el único host donde se acepta el login de un `platform_admin` (#53, S1.6 C8): en cualquier
    otro host no-tenant el login de plataforma se rechaza como una credencial inexistente.
    """
    return _first_label(host, base_domain, allow_localhost=allow_localhost) in PLATFORM_SUBDOMAINS


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

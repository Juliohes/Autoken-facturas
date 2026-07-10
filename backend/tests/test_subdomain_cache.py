"""Tests de la caché de resolución de subdominio (#52).

Función pura, sin BD: el resolver es un espía en memoria y el reloj es inyectable, así los criterios
son deterministas. Cubren: el hit negativo no vuelve a consultar; el positivo NO se cachea (para la
revocación instantánea de un tenant suspendido); el TTL expira; la cota LRU acota el tamaño.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from tenancy.resolution import ResolvedTenant
from tenancy.resolution_cache import NegativeTenantResolutionCache


class _Clock:
    """Reloj monotónico inyectable para controlar el TTL sin dormir."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _tenant(slug: str) -> ResolvedTenant:
    return ResolvedTenant(id=uuid4(), slug=slug, name=slug.upper(), is_demo=False)


async def test_hit_negativo_no_vuelve_a_consultar_la_bd() -> None:
    """Un slug inexistente ya visto se sirve de caché: el resolver (BD) no se llama la 2ª vez."""
    calls: list[str] = []

    async def resolver(slug: str) -> ResolvedTenant | None:
        calls.append(slug)
        return None

    cache = NegativeTenantResolutionCache(resolver, ttl_seconds=30, max_size=16)
    assert await cache.resolve("nope") is None
    assert await cache.resolve("nope") is None
    assert calls == ["nope"]  # solo la primera consultó la BD


async def test_positivo_no_se_cachea_para_revocacion_instantanea() -> None:
    """Un tenant activo NO se cachea: si se suspende, deja de resolver al instante (C23)."""
    state: dict[str, object] = {"value": _tenant("ilex"), "calls": 0}

    async def resolver(slug: str) -> ResolvedTenant | None:
        state["calls"] = int(state["calls"]) + 1  # type: ignore[arg-type]
        return state["value"]  # type: ignore[return-value]

    cache = NegativeTenantResolutionCache(resolver, ttl_seconds=30, max_size=16)
    primero = await cache.resolve("ilex")
    assert primero is not None and primero.slug == "ilex"

    state["value"] = None  # el tenant se suspende entre peticiones
    assert await cache.resolve("ilex") is None  # se ve de inmediato, no venía cacheado
    assert state["calls"] == 2  # ambas consultaron la BD (el positivo no se memoriza)


async def test_el_ttl_expira_el_veredicto_negativo() -> None:
    """Pasado el TTL, un negativo cacheado se vuelve a consultar (staleness acotada)."""
    clock = _Clock()
    calls: list[str] = []

    async def resolver(slug: str) -> ResolvedTenant | None:
        calls.append(slug)
        return None

    cache = NegativeTenantResolutionCache(resolver, ttl_seconds=30, max_size=16, clock=clock)
    assert await cache.resolve("nope") is None
    clock.now = 31  # más allá del TTL
    assert await cache.resolve("nope") is None
    assert calls == ["nope", "nope"]  # tras expirar, re-consulta


async def test_la_cota_lru_acota_el_tamano() -> None:
    """Con la caché llena, la entrada menos usada se evicta y se re-consulta al volver a pedirla."""
    calls: list[str] = []

    async def resolver(slug: str) -> ResolvedTenant | None:
        calls.append(slug)
        return None

    cache = NegativeTenantResolutionCache(resolver, ttl_seconds=1000, max_size=2)
    await cache.resolve("a")
    await cache.resolve("b")
    await cache.resolve("c")  # desborda: evicta "a" (la menos usada)
    calls.clear()
    assert await cache.resolve("b") is None  # sigue en caché: no consulta
    assert await cache.resolve("a") is None  # fue evictada: re-consulta
    assert calls == ["a"]


def test_max_size_invalido_falla_fuerte() -> None:
    """`max_size < 1` es un error de configuración: falla al construir (fail-loud), sin silencio."""

    async def resolver(slug: str) -> ResolvedTenant | None:
        return None

    with pytest.raises(ValueError):
        NegativeTenantResolutionCache(resolver, ttl_seconds=1, max_size=0)

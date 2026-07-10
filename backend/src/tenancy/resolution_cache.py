"""Caché de resolución subdominio->tenant: adaptador anti-DoS/enumeración sobre `resolve_tenant`.

`resolve_tenant(slug)` consulta la BD en CADA petición, incluso no autenticada. Sin caché, un
atacante puede martillear subdominios (DoS a la BD) y medir tiempos (enumeración) probando slugs al
azar, casi todos inexistentes. Esta caché absorbe esa carga.

DECISIÓN DE SEGURIDAD (ADR-0014): se cachea SOLO el veredicto NEGATIVO (slug que no resuelve). Es
justo el patrón del ataque pre-auth: un atacante prueba subdominios que no existen; cachear que "no
resuelve" elimina la carga de BD de las repeticiones y no revela nada. Los resultados POSITIVOS
(tenant activo) NUNCA se cachean, a propósito: así una suspensión de tenant surte efecto AL INSTANTE
(invariante C23 de S1.3: revocación inmediata), sin ventana de staleness en la autorización, que es
lo que importa de verdad. La única staleness que introduce es benigna y acotada por el TTL: un
tenant recién CREADO puede tardar hasta `ttl` segundos en empezar a resolver.

Compromiso asumido y documentado: como los positivos no se cachean, una petición a un tenant real
consulta la BD cada vez, mientras que un slug inexistente ya visto responde de caché. Eso deja un
canal de temporización teórico (existente = más lento que inexistente-cacheado); es débil (la
consulta es una función indexada `SECURITY DEFINER`, sub-milisegundo, ahogada por el jitter de red)
y se acepta frente al requisito duro de revocación instantánea de un tenant suspendido.

SOLID: el middleware depende de la interfaz `resolve(slug)`, no de esta implementación; la caché es
un adaptador que envuelve cualquier resolver `async (str) -> ResolvedTenant | None`. Acotada en
tiempo (TTL corto configurable) y en tamaño (LRU con cota dura).
"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from tenancy.resolution import ResolvedTenant

# Resolver que envuelve la caché: dado un slug, devuelve su tenant activo o `None` si no resuelve.
Resolver = Callable[[str], Awaitable[ResolvedTenant | None]]


class NegativeTenantResolutionCache:
    """Caché LRU con TTL del veredicto "este slug NO resuelve" sobre un resolver de tenants.

    Solo memoriza negativos (ver la nota de seguridad del módulo). Segura para uso concurrente: un
    `asyncio.Lock` protege la estructura, pero el resolver se invoca FUERA del lock para no
    serializar todas las resoluciones tras una consulta lenta a la BD.
    """

    def __init__(
        self,
        resolver: Resolver,
        *,
        ttl_seconds: float,
        max_size: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_size < 1:
            raise ValueError("max_size de la caché de resolución debe ser >= 1")
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds de la caché de resolución no puede ser negativo")
        self._resolver = resolver
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._clock = clock
        # slug -> instante monotónico de expiración del veredicto negativo. OrderedDict = orden LRU:
        # el más reciente al final, el menos usado al principio (candidato a evicción).
        self._negatives: OrderedDict[str, float] = OrderedDict()
        self._lock = asyncio.Lock()

    async def resolve(self, slug: str) -> ResolvedTenant | None:
        """Resuelve `slug` sirviendo de caché los negativos vivos; consulta la BD en el resto."""
        now = self._clock()
        async with self._lock:
            expires_at = self._negatives.get(slug)
            if expires_at is not None:
                if expires_at > now:
                    self._negatives.move_to_end(slug)  # refresca su posición LRU (uso reciente)
                    return None  # hit negativo: no se toca la BD
                del self._negatives[slug]  # entrada expirada: se re-consultará abajo

        # Miss (o positivo, que nunca se cachea): se resuelve contra la BD. Fuera del lock a
        # propósito. Si el resolver lanza (BD caída), la excepción se propaga y NADA se cachea:
        # un fallo de infraestructura no se enmascara como "no resuelve" (fail-loud).
        tenant = await self._resolver(slug)
        if tenant is None:
            async with self._lock:
                self._negatives[slug] = self._clock() + self._ttl
                self._negatives.move_to_end(slug)
                while len(self._negatives) > self._max_size:
                    self._negatives.popitem(last=False)  # evicta el menos usado (cota de memoria)
        return tenant

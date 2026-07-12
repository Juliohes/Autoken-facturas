"""Resolver BORME (L3, enriquecimiento CIF->razón social de sociedades; no autoritativo).

Adaptador HTTP público sobre OpenMercantil/LibreBOR (datos del Boletín Oficial del Registro
Mercantil). Enriquece un CIF de **sociedad** con su denominación registral. No cubre autónomos ni
es autoritativo del par CIF+nombre (`negative_authoritative=False`): un CIF que BORME no encuentre
no se invalida (un autónomo válido no está en el Mercantil); solo aporta cuando responde.

En CI va doblado (sin red). La llamada real solo se ejerce en staging (`settings.borme_base_url`).
"""

from __future__ import annotations

import httpx

from shared.config import Settings
from shared.logging import get_logger

from .base import ResolutionResult, ResolverUnavailable

_logger = get_logger("counterparty.resolvers")


class BormeResolver:
    """Fuente BORME (OpenMercantil/LibreBOR) tras la interfaz `CifResolver`.

    Consulta HTTP con `httpx` y timeout. Un 404 se interpreta como "no consta en el Mercantil"
    (`exists=False`, no autoritativo); cualquier otro fallo (red, timeout, 5xx, parseo) se **loguea
    a warning** (fuente + causa, sin secretos) y se traduce a `ResolverUnavailable`, para que la
    fuente se degrade a no disponible con rastro, nunca en silencio.
    """

    source = "borme"
    negative_authoritative = False

    def __init__(self, settings: Settings) -> None:
        if not settings.borme_base_url:
            raise ResolverUnavailable("BORME no configurado (falta borme_base_url)")
        self._base_url = settings.borme_base_url.rstrip("/")
        self._timeout = settings.borme_timeout

    async def resolve(self, cif: str, name_read: str | None) -> ResolutionResult:
        url = f"{self._base_url}/empresa/{cif}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
            if response.status_code == httpx.codes.NOT_FOUND:
                return ResolutionResult(exists=False, official_name=None)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:  # noqa: BLE001  (fallo real = fuente no disponible; se loguea antes)
            _logger.warning(
                "cif_resolver_unavailable",
                source=self.source,
                cause=str(exc),
                error_type=type(exc).__name__,
            )
            raise ResolverUnavailable(f"BORME no disponible: {exc}") from exc
        # El nombre registral llega en `denominacion` (OpenMercantil); la comparación de nombre la
        # hace el servicio (con la razón social oficial), que la fuente no realiza.
        official_name = payload.get("denominacion") or payload.get("name") or None
        return ResolutionResult(exists=True, official_name=official_name)

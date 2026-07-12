"""Contrato común de los resolvers externos del CIF (L3) + envoltorio de ejecución bloqueante.

Un `CifResolver` es el adaptador de una fuente externa (AEAT censal, VIES, BORME) tras una interfaz
uniforme: `resolve(cif, name_read) -> ResolutionResult`. El servicio orquestador (`counterparty.
service`) depende SOLO de esta interfaz, nunca de un cliente concreto, de modo que las fuentes se
pueden doblar en test y añadir/cambiar sin tocar la lógica de veredicto.

Semántica de disponibilidad: una caída/timeout de la fuente se señala lanzando `ResolverUnavailable`
(o `TimeoutError`); el servicio la trata como "fuente no disponible" (salta a la siguiente y NO
cachea), nunca como "el CIF no existe". Un `ResolutionResult(exists=False)` es una respuesta
afirmativa de la fuente ("este CIF no consta"), cosa muy distinta de no haber podido preguntar.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from shared.logging import get_logger

_logger = get_logger("counterparty.resolvers")


class ResolverUnavailable(Exception):
    """La fuente externa no pudo responder (timeout, red, error del servicio).

    NO significa "el CIF no existe": significa "no se pudo preguntar". El servicio la captura y
    degrada esa fuente a no disponible (regla de disponibilidad de S2.8), sin cachear nada.
    """


@dataclass(frozen=True)
class ResolutionResult:
    """Respuesta normalizada de una fuente externa sobre un CIF.

    - `exists`: la fuente afirma que el CIF consta (`True`) o que no consta (`False`).
    - `official_name`: razón social oficial devuelta por la fuente (o `None` si no la da).

    La coincidencia del nombre NO viaja aquí a propósito: el servicio la calcula SIEMPRE con
    `names.compare_names(name_read, official_name)`, igual en la ruta fresca y en la cacheada, para
    que el veredicto no dependa de si hubo caché ni del matching propio de cada fuente.
    """

    exists: bool
    official_name: str | None = None


@runtime_checkable
class CifResolver(Protocol):
    """Interfaz de una fuente externa de verificación de CIF.

    `source` es la etiqueta de la fuente (`"aeat"`/`"vies"`/`"borme"`), que casa con las claves de
    `tenants.cif_sources` y con la columna `source` de la caché. `negative_authoritative` marca si
    un `exists=False` de esta fuente es determinante (AEAT censal, autoritativa del par CIF+nombre)
    o no (VIES/BORME: su "no consta" no invalida, solo aporta).
    """

    source: str
    negative_authoritative: bool

    async def resolve(self, cif: str, name_read: str | None) -> ResolutionResult:
        """Consulta la fuente. Lanza `ResolverUnavailable`/`TimeoutError` si no puede responder."""
        ...


async def run_blocking[T](fn: Callable[[], T], *, source: str) -> T:
    """Corre la llamada bloqueante del resolver en un hilo y traduce fallos a `ResolverUnavailable`.

    Envoltorio ÚNICO de los resolvers SOAP (AEAT/VIES), cuyos clientes son bloqueantes: corre `fn`
    en un hilo para no bloquear el event loop. Un `ResolverUnavailable` se propaga tal cual;
    cualquier otro fallo (red, timeout, parseo, cambio de esquema del servicio) se **loguea a
    warning** (fuente y causa, SIN secretos: nada de certificado ni contraseña) y se convierte en
    `ResolverUnavailable`: la fuente se degrada a no disponible CON rastro, nunca en silencio.
    """
    try:
        return await asyncio.to_thread(fn)
    except ResolverUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001  (fallo real = fuente no disponible; se loguea antes)
        _logger.warning(
            "cif_resolver_unavailable",
            source=source,
            cause=str(exc),
            error_type=type(exc).__name__,
        )
        raise ResolverUnavailable(f"{source} no disponible: {exc}") from exc

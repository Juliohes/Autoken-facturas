"""Servicio de verificación del CIF de contraparte (S2.8): orquesta L1-L4 y produce el veredicto.

Orden barato->autoritativo (S2.8 §4): L1 estructura (mód-23) -> L2 supplier master del tenant -> L3
fuentes externas habilitadas, en orden, cada una pasando por L4 (caché global) antes de llamar. Se
corta en cuanto hay veredicto suficiente. Regla de disponibilidad: la caída/timeout de un tercero
degrada a `unverified` (revisar manual), jamás a `invalid`/`not_found`, y no se cachea el fallo.

El servicio abre su PROPIA sesión con contexto de tenant (`shared.db.tenant_session`, rol runtime,
RLS aplica) y no conoce los clientes externos concretos, solo la interfaz `CifResolver`: en test se
inyectan dobles; en producción (`resolvers=None`) se construyen los reales desde `settings`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from shared.config import Settings, get_settings
from shared.db import tenant_session
from shared.logging import get_logger
from shared.tax_id import normalize_tax_id, validate_tax_id

from .constants import CifStatus
from .names import compare_names
from .repository import (
    get_fresh_lookup,
    get_supplier_master,
    get_tenant_cif_sources,
    upsert_lookup,
    upsert_supplier_master,
)
from .resolvers.base import CifResolver, ResolverUnavailable

_logger = get_logger("counterparty.service")

# Conjunto de fuentes por defecto cuando `tenants.cif_sources` es NULL (S2.8 §2). El orden importa:
# supplier master primero (gratis), luego AEAT (autoritativa), VIES (intra-UE) y BORME (enriquece).
DEFAULT_SOURCES: tuple[str, ...] = ("supplier_master", "aeat", "vies", "borme")
_SUPPLIER_MASTER = "supplier_master"

# Fuente de indisponibilidad tratada como "no se pudo preguntar" (nunca como "no existe").
_UNAVAILABLE_ERRORS = (TimeoutError, ResolverUnavailable)


@dataclass(frozen=True)
class CounterpartyVerdict:
    """Veredicto estructurado que consume la pantalla de confirmación (S2.4).

    `status`: `valid` (existe; ver `name_match`), `invalid` (estructura KO o no concuerda de forma
    que invalida: bloquea), `not_found` (fuente autoritativa afirma que no existe: bloquea),
    `unverified` (ninguna fuente pudo resolver: revisar manual, no bloquea). `name_match` es `None`
    cuando no aplica/no se pudo comparar. `source` identifica quién decidió; `reason` explica el
    estado en español.

    `checked_sources` = fuentes **externas** realmente consultadas (llamada al resolver —con éxito o
    fallida— o hit de caché), en orden. NO incluye el `supplier_master` (no es externa) ni las
    fuentes saltadas por no tener resolver disponible.
    """

    status: str
    name_match: bool | None
    official_name: str | None
    source: str
    checked_sources: tuple[str, ...]
    reason: str | None


def _as_uuid(tenant_id: str | UUID) -> UUID:
    """Acepta el `tenant_id` como str (viene del contexto de la petición) o ya como UUID."""
    return tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))


def _build_real_resolver(source: str, settings: Settings) -> CifResolver:
    """Construye el resolver REAL de una fuente desde `settings` (solo producción; nunca en CI)."""
    # Import perezoso: los clientes reales (zeep/httpx) solo se cargan cuando se usan de verdad.
    if source == "aeat":
        from .resolvers.aeat import AeatCensalResolver

        return AeatCensalResolver(settings)
    if source == "vies":
        from .resolvers.vies import ViesResolver

        return ViesResolver(settings)
    if source == "borme":
        from .resolvers.borme import BormeResolver

        return BormeResolver(settings)
    raise ResolverUnavailable(f"Fuente externa desconocida: {source!r}")


def _resolver_for(
    source: str, resolvers: dict[str, CifResolver] | None, settings: Settings
) -> CifResolver | None:
    """Resuelve qué adaptador usar para una fuente.

    Con `resolvers` inyectado (test), se usa el del diccionario; una fuente ausente devuelve `None`
    (se trata como no disponible: no se construye un cliente real que tocaría la red en CI). Con
    `resolvers=None` (producción) se construye el real desde `settings`; si no está configurado,
    `None` (fuente no disponible).
    """
    if resolvers is not None:
        return resolvers.get(source)
    try:
        return _build_real_resolver(source, settings)
    except ResolverUnavailable:
        return None


async def verify_counterparty(
    tenant_id: str | UUID,
    cif: str | None,
    name_read: str | None,
    *,
    resolvers: dict[str, CifResolver] | None = None,
) -> CounterpartyVerdict:
    """Verifica el CIF de la contraparte y devuelve un `CounterpartyVerdict` (S2.8, C1-C11)."""
    # L1 - estructura (mód-23). KO -> invalid sin tocar red ni caché (C1).
    structure = validate_tax_id(cif)
    if not structure.valid:
        return CounterpartyVerdict(
            status=CifStatus.INVALID,
            name_match=None,
            official_name=None,
            source="structure",
            checked_sources=(),
            reason=structure.reason,
        )
    canonical = normalize_tax_id(cif)
    settings = get_settings()

    async with tenant_session(_as_uuid(tenant_id)) as session:
        # L2 - supplier master del tenant (gratis, corta antes de L3). C2/C3.
        master = await get_supplier_master(session, cif=canonical)
        if master is not None:
            return CounterpartyVerdict(
                status=CifStatus.VALID,
                name_match=compare_names(name_read, master.name),
                official_name=master.name,
                source=_SUPPLIER_MASTER,
                checked_sources=(),  # L2 corta antes de L3: no se consultó ninguna fuente externa
                reason=None,
            )

        # L3 - fuentes externas habilitadas (en orden), cada una tras L4 (caché).
        enabled = await get_tenant_cif_sources(session)
        sources = list(enabled) if enabled is not None else list(DEFAULT_SOURCES)
        external = [s for s in sources if s != _SUPPLIER_MASTER]
        checked: list[str] = []

        for source in external:
            resolver = _resolver_for(source, resolvers, settings)
            if resolver is None:
                continue  # fuente no inyectada/no configurada: no disponible, se salta
            checked.append(source)

            # L4 - caché global vigente: usa la entrada sin llamar (C7a/C8).
            cached = await get_fresh_lookup(session, cif=canonical, source=source)
            if cached is not None:
                exists, official_name = cached.exists, cached.official_name
            else:
                try:
                    result = await resolver.resolve(canonical, name_read)
                except _UNAVAILABLE_ERRORS as exc:
                    # Caída/timeout: fuente no disponible, NO se cachea (C9). Se loguea para no
                    # degradar a `unverified` en silencio (un bug de parseo o un cambio de esquema
                    # de la fuente debe dejar rastro). Sin secretos.
                    _logger.warning(
                        "cif_source_unavailable",
                        source=source,
                        cause=str(exc),
                        error_type=type(exc).__name__,
                    )
                    continue
                exists, official_name = result.exists, result.official_name
                await upsert_lookup(
                    session,
                    cif=canonical,
                    source=source,
                    exists=exists,
                    official_name=official_name,
                    raw={},
                    ttl_seconds=settings.cif_cache_ttl_seconds,
                )

            if exists:
                # `name_match` se calcula SIEMPRE localmente (ruta fresca y cacheada por igual), así
                # el veredicto no depende de si hubo caché ni del matching propio de la fuente.
                return CounterpartyVerdict(
                    status=CifStatus.VALID,
                    name_match=compare_names(name_read, official_name),
                    official_name=official_name,
                    source=source,
                    checked_sources=tuple(checked),
                    reason=None,
                )
            # exists=False: solo la fuente AUTORITATIVA en negativo produce not_found (C6/C10).
            if resolver.negative_authoritative:
                return CounterpartyVerdict(
                    status=CifStatus.NOT_FOUND,
                    name_match=None,
                    official_name=official_name,
                    source=source,
                    checked_sources=tuple(checked),
                    reason="El CIF no consta en el censo de la fuente autoritativa (AEAT).",
                )
            # Fuente no autoritativa que dice "no consta": no invalida, sigue a la siguiente.

        # Agotadas las fuentes sin veredicto: revisar manual. Nunca invalid/not_found por un 3.º.
        return CounterpartyVerdict(
            status=CifStatus.UNVERIFIED,
            name_match=None,
            official_name=None,
            source="none",
            checked_sources=tuple(checked),
            reason="Ninguna fuente habilitada pudo verificar el CIF; revisar manualmente.",
        )


@asynccontextmanager
async def _session_for(
    tenant_id: str | UUID, session: AsyncSession | None
) -> AsyncIterator[AsyncSession]:
    """Cede la sesión inyectada (participa en la transacción del llamante) o abre una propia.

    Con `session` inyectada (p. ej. la de la petición en `invoicing.confirm`), el upsert corre en la
    MISMA transacción que el resto de la confirmación (atomicidad, spec S2.5 §4). Sin ella (llamada
    suelta de S2.8), se abre una `tenant_session` con el contexto del tenant, como hasta ahora.
    """
    if session is not None:
        yield session
    else:
        async with tenant_session(_as_uuid(tenant_id)) as own:
            yield own


async def record_confirmation(
    tenant_id: str | UUID,
    cif: str,
    name: str,
    *,
    source: str = "human",
    session: AsyncSession | None = None,
) -> None:
    """Registra una confirmación humana en el supplier master del tenant (upsert, C12).

    Alimenta L2: una verificación posterior de ese CIF en el mismo tenant acertará sin red. Aislado
    por tenant (RLS): lo que una asesoría confirma NO lo heredan las demás.

    `session` inyectada -> el upsert participa en esa transacción (la de la petición, para que la
    confirmación sea atómica, S2.5 §4); `None` -> abre su propia `tenant_session` (uso suelto S2.8).

    Valida la estructura del CIF (mód-23) ANTES de sembrar: no se mete basura estructural en
    `counterparties` (el master es fuente autoritativa de L2). Un CIF inválido se rechaza con
    `ValueError` (fail-loud), no se guarda a medias.
    """
    structure = validate_tax_id(cif)
    if not structure.valid:
        raise ValueError(
            f"No se puede confirmar un CIF estructuralmente inválido: {structure.reason}"
        )
    canonical = normalize_tax_id(cif)
    async with _session_for(tenant_id, session) as sess:
        await upsert_supplier_master(sess, cif=canonical, name=name, name_source=source)

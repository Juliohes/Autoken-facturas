"""Utilidades de test para la verificación del CIF de contraparte (S2.8, spec docs/specs/S2.8).

No es un módulo de tests (prefijo `_`): siembra de supplier master (`counterparties`) y de la caché
global (`cif_lookups`), resolvers doblados (sin red), y helpers para invocar el servicio y consultar
el efecto.

Contrato que el `implementer` debe respetar (lo fija esta fase roja):
- Servicio: `counterparty.service.verify_counterparty(tenant_id, cif, name_read, *, resolvers=None)`
  (coroutine; abre su propia sesión con contexto de tenant). Devuelve un `CounterpartyVerdict` con
  `status` ∈ {"valid","invalid","not_found","unverified"}, `name_match` (bool|None), `official_name`
  (str|None), `source` (str) y `checked_sources` (tupla).
- `counterparty.service.record_confirmation(tenant_id, cif, name, *, settings, source="human")`:
  upsert del supplier master (incrementa `times_seen` en confirmaciones repetidas). `cif`/`name`
  viven cifrados desde S5.2 (`counterparties.cif`/`name`, pgcrypto por tenant + índice ciego del
  CIF).
- Resolver: objeto con `.source` (str), `.negative_authoritative` (bool) y
  `async resolve(cif, name_read) -> result` con atributos `exists` (bool), `official_name`
  (str|None), `name_match` (bool|None). Un timeout/caída se señala lanzando `TimeoutError` (lo trata
  como fuente no disponible; NUNCA como "no existe").
- Feature flags por tenant: columna `cif_sources` (JSONB) en `tenants` (null = por defecto
  ["supplier_master","aeat","vies","borme"]).
- `cif_lookups` es GLOBAL (sin tenant_id); `counterparties` va por tenant (RLS).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import asyncpg

# CIFs de prueba (mód-23): válidos y uno inválido.
VALID_CIF = "A39031620"
VALID_CIF_2 = "B06183446"
INVALID_CIF = "A39031621"  # letra/dígito de control equivocado


@dataclass
class _FakeResult:
    exists: bool
    official_name: str | None = None
    name_match: bool | None = None


@dataclass
class FakeResolver:
    """Doble de una fuente externa (AEAT/VIES/BORME) sin red.

    `unavailable=True` -> lanza TimeoutError al resolver (simula caída/timeout).
    `negative_authoritative` True para AEAT (su "no existe" es determinante); False para VIES/BORME
    (su negativo no invalida).
    """

    source: str
    exists: bool | None = None
    official_name: str | None = None
    name_match: bool | None = None
    unavailable: bool = False
    negative_authoritative: bool = False
    calls: list = field(default_factory=list)

    async def resolve(self, cif: str, name_read: str | None) -> _FakeResult:
        self.calls.append((cif, name_read))
        if self.unavailable:
            raise TimeoutError(f"{self.source} no disponible (test)")
        return _FakeResult(
            exists=bool(self.exists), official_name=self.official_name, name_match=self.name_match
        )


# --- Siembra (superusuario, saltando RLS) --------------------------------------------------------
async def seed_counterparty(
    dsns: dict[str, str],
    *,
    tenant_id: str,
    cif: str,
    name: str,
    source: str = "human",
    times_seen: int = 1,
) -> None:
    """Inserta una fila en el supplier master del tenant (`counterparties`).

    `cif`/`name` viven cifrados desde S5.2 (`pgp_sym_encrypt`, clave derivada por tenant) más un
    índice ciego del CIF. Se cifra con la MISMA clave maestra que usará la aplicación bajo test.
    """
    from shared.config import get_settings
    from shared.encryption import derive_tenant_encryption_key
    from tests._dbtest import cif_blind_index_for

    key = derive_tenant_encryption_key(get_settings().db_encryption_master_key, tenant_id)
    idx = cif_blind_index_for(tenant_id, cif)
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "INSERT INTO counterparties "
            "(tenant_id, cif, cif_blind_index, name, name_source, times_seen, verified_at) "
            "VALUES ($1, pgp_sym_encrypt($2, $3), $4, pgp_sym_encrypt($5, $3), $6, $7, now())",
            tenant_id,
            cif,
            key,
            idx,
            name,
            source,
            times_seen,
        )
    finally:
        await conn.close()


async def set_cif_sources(dsns: dict[str, str], *, tenant_id: str, sources: list[str]) -> None:
    """Fija los feature flags de fuentes del tenant (`tenants.cif_sources`)."""
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "UPDATE tenants SET cif_sources = $2::jsonb WHERE id = $1",
            tenant_id,
            json.dumps(sources),
        )
    finally:
        await conn.close()


async def seed_cif_lookup(
    dsns: dict[str, str],
    *,
    cif: str,
    source: str,
    exists: bool,
    official_name: str | None,
    fresh: bool = True,
) -> None:
    """Inserta una entrada en la caché GLOBAL (`cif_lookups`), fresca o caducada."""
    expires = datetime.now(UTC) + (timedelta(days=1) if fresh else timedelta(days=-1))
    conn = await asyncpg.connect(dsns["admin"])
    try:
        await conn.execute(
            "INSERT INTO cif_lookups (cif, source, exists, official_name, raw_json, fetched_at, "
            "expires_at) VALUES ($1,$2,$3,$4,'{}'::jsonb, now(), $5)",
            cif,
            source,
            exists,
            official_name,
            expires,
        )
    finally:
        await conn.close()


# --- Invocación del servicio (import perezoso) ---------------------------------------------------
async def verify(
    dsns: dict[str, str], *, tenant_id: str, cif: str, name_read: str | None, resolvers
):
    """Llama a `counterparty.service.verify_counterparty` (import perezoso; sin red)."""
    from counterparty.service import verify_counterparty

    return await verify_counterparty(tenant_id, cif, name_read, resolvers=resolvers)


async def confirm(dsns: dict[str, str], *, tenant_id: str, cif: str, name: str) -> None:
    from counterparty.service import record_confirmation
    from shared.config import get_settings

    await record_confirmation(tenant_id, cif, name, settings=get_settings())


# --- Consultas de efecto -------------------------------------------------------------------------
async def fetch_counterparty(dsns: dict[str, str], *, tenant_id: str, cif: str) -> dict | None:
    """Fila de `counterparties` por su CIF (buscado por índice ciego, S5.2; `name`/`cif`
    descifrados)."""
    from shared.config import get_settings
    from shared.encryption import derive_tenant_encryption_key
    from tests._dbtest import cif_blind_index_for

    key = derive_tenant_encryption_key(get_settings().db_encryption_master_key, tenant_id)
    idx = cif_blind_index_for(tenant_id, cif)
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "SELECT id, tenant_id, pgp_sym_decrypt(cif, $2)::text AS cif, "
            "pgp_sym_decrypt(name, $2)::text AS name, name_source, times_seen, verified_at "
            "FROM counterparties WHERE tenant_id = $1 AND cif_blind_index = $3",
            tenant_id,
            key,
            idx,
        )
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def fetch_cif_lookup(dsns: dict[str, str], *, cif: str, source: str) -> dict | None:
    conn = await asyncpg.connect(dsns["admin"])
    try:
        row = await conn.fetchrow(
            "SELECT * FROM cif_lookups WHERE cif = $1 AND source = $2", cif, source
        )
        return dict(row) if row is not None else None
    finally:
        await conn.close()


async def counterparties_visible_as_tenant(dsns: dict[str, str], *, tenant_id: str) -> int:
    """Filas de `counterparties` visibles bajo el rol runtime en un contexto de tenant (RLS)."""
    conn = await asyncpg.connect(dsns["app"])
    try:
        await conn.execute("SELECT set_config('app.tenant_id', $1, false)", tenant_id)
        await conn.execute("SELECT set_config('app.company_id', '', false)")
        return int(await conn.fetchval("SELECT count(*) FROM counterparties"))
    finally:
        await conn.close()

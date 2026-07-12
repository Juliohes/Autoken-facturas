"""Acceso a datos de S2.8: SQL de `counterparties` (por tenant) y `cif_lookups` (caché global).

La sesión llega ya abierta en el contexto de aislamiento del tenant (`shared.db.tenant_session`): en
`counterparties` la RLS de S1.1 decide qué filas se ven/escriben, así que las consultas NO filtran
ni insertan `tenant_id` por parámetro: sale de `app.tenant_id` (misma fuente que la RLS), como en
`ocr.repository`. `cif_lookups` es GLOBAL (sin RLS de tenant): se lee/escribe por `(cif, source)` y
es visible entre asesorías (solo datos públicos, ADR-0011).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# `tenant_id` de la escritura derivado del contexto de la sesión (coherente con la RLS), nunca por
# parámetro: ninguna fila cruza el tenant de la petición.
_TENANT_FROM_CONTEXT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"


@dataclass(frozen=True)
class SupplierMasterRow:
    """Fila del supplier master del tenant (razón social confirmada + su procedencia)."""

    name: str
    name_source: str


@dataclass(frozen=True)
class CifLookupRow:
    """Entrada vigente de la caché global de resoluciones (`exists` + razón social oficial)."""

    exists: bool
    official_name: str | None


# --- Supplier master (`counterparties`, por tenant vía RLS) --------------------------------------
_SELECT_MASTER = text("SELECT name, name_source FROM counterparties WHERE cif = :cif")

# Upsert de confirmación (C12): en conflicto por `(tenant_id, cif)` incrementa `times_seen` y
# refresca nombre, procedencia y `verified_at`. El `tenant_id` sale del contexto (como la RLS).
_UPSERT_MASTER = text(
    f"INSERT INTO counterparties (tenant_id, cif, name, name_source, times_seen, verified_at) "
    f"VALUES ({_TENANT_FROM_CONTEXT}, :cif, :name, :name_source, 1, now()) "
    f"ON CONFLICT (tenant_id, cif) DO UPDATE SET "
    f"  times_seen = counterparties.times_seen + 1, "
    f"  name = EXCLUDED.name, "
    f"  name_source = EXCLUDED.name_source, "
    f"  verified_at = now()"
)

# --- Feature flags de fuentes (`tenants.cif_sources`, tenant del contexto vía RLS) ---------------
_SELECT_CIF_SOURCES = text("SELECT cif_sources FROM tenants")

# --- Caché global de resoluciones (`cif_lookups`, sin tenant) ------------------------------------
# Solo la entrada VIGENTE (TTL no vencido): una entrada caducada equivale a "no hay caché" y fuerza
# el refetch (C7b). `exists` va entrecomillado por ser palabra reservada.
_SELECT_FRESH_LOOKUP = text(
    'SELECT "exists", official_name FROM cif_lookups '
    "WHERE cif = :cif AND source = :source AND expires_at > now()"
)

# Cachea (o refresca) la resolución de una fuente. `expires_at` = ahora + TTL configurable (L4).
_UPSERT_LOOKUP = text(
    "INSERT INTO cif_lookups "
    '(cif, source, "exists", official_name, raw_json, fetched_at, expires_at) '
    "VALUES (:cif, :source, :exists, :official_name, CAST(:raw AS jsonb), now(), "
    "        now() + make_interval(secs => :ttl_seconds)) "
    "ON CONFLICT (cif, source) DO UPDATE SET "
    '  "exists" = EXCLUDED."exists", '
    "  official_name = EXCLUDED.official_name, "
    "  raw_json = EXCLUDED.raw_json, "
    "  fetched_at = now(), "
    "  expires_at = EXCLUDED.expires_at"
)


async def get_supplier_master(session: AsyncSession, *, cif: str) -> SupplierMasterRow | None:
    """Busca el CIF en el supplier master del tenant del contexto (L2). `None` si no está."""
    row = (await session.execute(_SELECT_MASTER, {"cif": cif})).first()
    if row is None:
        return None
    return SupplierMasterRow(name=row.name, name_source=row.name_source)


async def upsert_supplier_master(
    session: AsyncSession, *, cif: str, name: str, name_source: str
) -> None:
    """Upserta la confirmación en el supplier master del tenant del contexto (times_seen++)."""
    await session.execute(_UPSERT_MASTER, {"cif": cif, "name": name, "name_source": name_source})


async def get_tenant_cif_sources(session: AsyncSession) -> list[str] | None:
    """Fuentes habilitadas del tenant (`tenants.cif_sources`); `None` = conjunto por defecto."""
    value = (await session.execute(_SELECT_CIF_SOURCES)).scalar_one_or_none()
    if value is None:
        return None
    # JSONB llega ya deserializado (asyncpg): se espera una lista de nombres de fuente.
    return list(value)


async def get_fresh_lookup(session: AsyncSession, *, cif: str, source: str) -> CifLookupRow | None:
    """Entrada de caché VIGENTE (TTL no vencido) para `(cif, source)`; `None` si no hay o caducó."""
    row = (await session.execute(_SELECT_FRESH_LOOKUP, {"cif": cif, "source": source})).first()
    if row is None:
        return None
    return CifLookupRow(exists=row.exists, official_name=row.official_name)


async def upsert_lookup(
    session: AsyncSession,
    *,
    cif: str,
    source: str,
    exists: bool,
    official_name: str | None,
    raw: dict[str, Any],
    ttl_seconds: int,
) -> None:
    """Cachea/refresca en la caché global la resolución de una fuente (con su TTL)."""
    await session.execute(
        _UPSERT_LOOKUP,
        {
            "cif": cif,
            "source": source,
            "exists": exists,
            "official_name": official_name,
            "raw": json.dumps(raw),
            "ttl_seconds": ttl_seconds,
        },
    )

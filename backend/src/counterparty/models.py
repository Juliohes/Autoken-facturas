"""Modelos ORM de S2.8: `counterparties` (supplier master) y `cif_lookups` (caché global).

El esquema aquí debe coincidir con la migración 0006 (el guard `alembic check` de CI detecta la
deriva ORM<->migración). Las políticas RLS y los grants viven en la migración, no en el ORM.

- `counterparties`: supplier master **por tenant** (RLS por `tenant_id`, patrón de `companies`), lo
  que cada asesoría confirma vale solo para ella. UNIQUE `(tenant_id, cif)`.
- `cif_lookups`: caché **GLOBAL** de resoluciones de fuentes públicas, **SIN** `tenant_id` ni RLS de
  tenant (ADR-0011). Solo datos de registros públicos; compartirla no cruza información de negocio.
  Clave `(cif, source)`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class Counterparty(Base):
    """CIF<->razón social ya confirmado por un humano de la asesoría (supplier master, por tenant).

    Primera línea de la verificación (L2): gratis y mejora con el uso. Aislada por `tenant_id` (RLS
    S1.1): lo que una asesoría confía NO lo heredan las demás. `times_seen` cuenta confirmaciones.
    """

    __tablename__ = "counterparties"
    __table_args__ = (
        UniqueConstraint("tenant_id", "cif", name="counterparties_tenant_cif_unique"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    cif: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    name_source: Mapped[str] = mapped_column(Text, nullable=False)
    times_seen: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CifLookup(Base):
    """Caché GLOBAL de una resolución externa de un CIF por una fuente pública (`(cif, source)`).

    Sin `tenant_id` ni RLS de tenant a propósito (ADR-0011): la razón social oficial de un CIF en un
    registro público es la misma para todos y no es dato de negocio de ninguna asesoría; compartirla
    ahorra cuota/latencia sin cruzar información. `expires_at` implementa el TTL (L4).
    """

    __tablename__ = "cif_lookups"

    # Clave natural `(cif, source)`: una entrada por CIF y fuente; sirve de PK y de unicidad.
    cif: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text, primary_key=True)
    # `exists` es palabra reservada en SQL: SQLAlchemy la entrecomilla; el atributo Python evita
    # ensombrecer el builtin usando el sufijo, mapeado a la columna real `exists`.
    exists_: Mapped[bool] = mapped_column("exists", Boolean, nullable=False)
    official_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

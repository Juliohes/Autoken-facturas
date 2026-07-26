"""Modelos ORM del núcleo de tenancy (S1.1).

Jerarquía: Plataforma -> Tenant (asesoría) -> Company (empresa cliente) -> User (empleado). Toda
tabla de negocio lleva `tenant_id` y RLS `FORCE` (ADR-0001); las políticas y los grants viven en la
migración (no se pueden expresar en el ORM). El esquema aquí y el de la migración deben coincidir.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base
from tenancy.constants import Role, UserStatus

_ROLES = tuple(role.value for role in Role)
_USER_STATUS = tuple(status.value for status in UserStatus)
_COMPANY_STATUS = ("active", "pending")
_TENANT_STATUS = ("active", "suspended")


def _pk() -> Mapped[UUID]:
    return mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )


class Tenant(Base):
    """Asesoría. `slug` es el subdominio (`<slug>.autoken.es`)."""

    __tablename__ = "tenants"
    __table_args__ = (CheckConstraint(f"status IN {_TENANT_STATUS}", name="tenants_status_valid"),)

    id: Mapped[UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(63), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    custom_domain: Mapped[str | None] = mapped_column(Text, unique=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    # Feature flags de fuentes de verificación del CIF de contraparte (S2.8, ADR-0011): lista de
    # fuentes habilitadas para el tenant. `NULL` = conjunto por defecto (supplier_master + aeat +
    # vies + borme). Las políticas/grants no cambian; la migración 0006 añade la columna.
    cif_sources: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Último export completo (S4.7, migración 0015): `NULL` si nunca se exportó. `delete_tenant`
    # exige que no sea `NULL` antes de poder borrar (spec S4.7 §3 decisión 4).
    last_export_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TenantBranding(Base):
    """Theming en runtime de una asesoría (logo, colores, nombre de la app)."""

    __tablename__ = "tenant_branding"

    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    logo_url: Mapped[str | None] = mapped_column(Text)
    color_primary: Mapped[str | None] = mapped_column(String(9))
    color_secondary: Mapped[str | None] = mapped_column(String(9))
    app_name: Mapped[str | None] = mapped_column(Text)
    favicon: Mapped[str | None] = mapped_column(Text)


class User(Base):
    """Usuario de un tenant. `role` decide el alcance; `status` gestiona la aprobación (S1.4).

    Un `platform_admin` no pertenece a ninguna asesoría (`tenant_id` nulo, S1.3): el CHECK
    `users_platform_admin_no_tenant` ata rol y pertenencia, y el índice único parcial da email
    único entre platform_admin (donde `UNIQUE(tenant_id, email)` no basta por los NULL distintos).
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="users_tenant_email_unique"),
        CheckConstraint(f"role IN {_ROLES}", name="users_role_valid"),
        CheckConstraint(f"status IN {_USER_STATUS}", name="users_status_valid"),
        CheckConstraint(
            "(role = 'platform_admin') = (tenant_id IS NULL)",
            name="users_platform_admin_no_tenant",
        ),
        Index("ix_users_tenant", "tenant_id", "id"),
        Index(
            "ux_users_platform_email",
            "email",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
        ),
    )

    id: Mapped[UUID] = _pk()
    tenant_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    totp_secret: Mapped[str | None] = mapped_column(Text)
    is_admin_tech: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Company(Base):
    """Empresa cliente de una asesoría. Se importan desde el Excel de la asesoría (S1.5).

    `cif`/`name` viven cifrados desde S5.2 (`pgp_sym_encrypt`, migración 0020): el ORM nunca los
    lee/escribe directamente (todo el acceso pasa por SQL crudo en `companies.repository`, con
    `pgp_sym_encrypt`/`pgp_sym_decrypt`), pero el esquema declarado aquí debe seguir coincidiendo
    con la migración real (`alembic check` lo exige) para que un futuro `--autogenerate` no
    proponga revertir el cifrado.
    """

    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "cif_blind_index", name="companies_tenant_cif_blind_index_unique"
        ),
        CheckConstraint(f"status IN {_COMPANY_STATUS}", name="companies_status_valid"),
        Index("ix_companies_tenant", "tenant_id", "id"),
    )

    id: Mapped[UUID] = _pk()
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    cif: Mapped[bytes] = mapped_column(BYTEA, nullable=False)
    cif_blind_index: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Membership(Base):
    """Pertenencia de un usuario a una empresa (un user puede estar en N empresas)."""

    __tablename__ = "memberships"
    __table_args__ = (Index("ix_memberships_tenant", "tenant_id", "company_id"),)

    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    company_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )


class AuditLog(Base):
    """Registro append-only de mutaciones. UPDATE/DELETE revocados al rol runtime (S1.8)."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_tenant", "tenant_id", "at"),)

    id: Mapped[UUID] = _pk()
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))
    payload_hash: Mapped[str | None] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

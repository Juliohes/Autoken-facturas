"""Núcleo de tenancy + aislamiento por RLS de dos niveles (S1.1, ADR-0001).

Crea el rol runtime restringido `autoken_app`, las tablas núcleo (tenants, tenant_branding, users,
companies, memberships, audit_log) y, sobre todas, RLS `FORCE` con políticas por `app.tenant_id` y
`app.company_id`. El rol runtime recibe DML sobre las tablas salvo en `audit_log`, que es append-only
(solo SELECT/INSERT). Las políticas y los grants van en SQL crudo porque el ORM no los expresa.

Revision ID: 0001_tenancy_core_rls
Revises:
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_tenancy_core_rls"
down_revision = None
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"

# Tablas con `tenant_id`: aislamiento por tenant + (opcional) por company vía `app.company_id`.
# `users`, `tenant_branding` y `audit_log` son **tenant-only a propósito**: un usuario pertenece a N
# empresas (vía `memberships`), no tiene una company única; el branding y la auditoría son de la
# asesoría entera. El filtrado fino por empresa de esos datos, si hace falta, es del RBAC (S1.6).
_TENANT_TABLES = ("tenant_branding", "users", "companies", "memberships", "audit_log")
# Columna por la que se acota al nivel empresa (segundo nivel). Para `companies` es su propio `id`
# (la empresa ES la fila); para `memberships`, la FK `company_id`. El resto no tienen segundo nivel.
_COMPANY_SCOPE_COLUMN = {"companies": "id", "memberships": "company_id"}
# Todas las tablas de negocio (para RLS FORCE y el guard C8).
_BUSINESS_TABLES = ("tenants", *_TENANT_TABLES)


def _uuid_pk() -> sa.Column:
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
    )


def upgrade() -> None:
    # 1) Rol runtime: restringido a propósito para que la RLS le aplique (no owner, sin BYPASSRLS).
    op.execute(
        f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{_APP_ROLE}') THEN
            CREATE ROLE {_APP_ROLE} NOLOGIN NOSUPERUSER NOINHERIT
              NOCREATEDB NOCREATEROLE NOBYPASSRLS;
          END IF;
        END $$;
        """
    )

    # 2) Tablas núcleo.
    op.create_table(
        "tenants",
        _uuid_pk(),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("custom_domain", sa.Text(), unique=True),
        sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active', 'suspended')", name="tenants_status_valid"),
    )
    op.create_table(
        "tenant_branding",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("logo_url", sa.Text()),
        sa.Column("color_primary", sa.String(9)),
        sa.Column("color_secondary", sa.String(9)),
        sa.Column("app_name", sa.Text()),
        sa.Column("favicon", sa.Text()),
    )
    op.create_table(
        "users",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text()),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("totp_secret", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "email", name="users_tenant_email_unique"),
        sa.CheckConstraint("role IN ('platform_admin', 'tenant_admin', 'user')", name="users_role_valid"),
        sa.CheckConstraint("status IN ('pending', 'active')", name="users_status_valid"),
    )
    op.create_index("ix_users_tenant", "users", ["tenant_id", "id"])
    op.create_table(
        "companies",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("cif", sa.String(16), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "cif", name="companies_tenant_cif_unique"),
        sa.CheckConstraint("status IN ('active', 'pending')", name="companies_status_valid"),
    )
    op.create_index("ix_companies_tenant", "companies", ["tenant_id", "id"])
    op.create_table(
        "memberships",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_memberships_tenant", "memberships", ["tenant_id", "company_id"])
    op.create_table(
        "audit_log",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("payload_hash", sa.Text()),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_log_tenant", "audit_log", ["tenant_id", "at"])

    # 3) RLS FORCE + políticas. `tenants` se aísla por su propio `id`; el resto por `tenant_id`,
    #    con segundo nivel opcional por company cuando la tabla tiene columna de company.
    _enable_rls("tenants", "id", company_column=None)
    for table in _TENANT_TABLES:
        _enable_rls(table, "tenant_id", company_column=_COMPANY_SCOPE_COLUMN.get(table))

    # 4) Grants al rol runtime (mínimo privilegio):
    #    - `tenants`: solo SELECT. El alta/baja/suspensión de asesorías es de plataforma, no de la
    #      API. Además, dar DELETE aquí permitiría borrar el tenant y arrastrar en cascada su
    #      `audit_log`, saltándose el append-only.
    #    - resto de tablas: DML completo salvo `audit_log`, append-only (solo SELECT/INSERT).
    op.execute(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT ON tenants TO {_APP_ROLE}")
    writable = ", ".join(t for t in _BUSINESS_TABLES if t not in ("tenants", "audit_log"))
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {writable} TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT ON audit_log TO {_APP_ROLE}")


def _enable_rls(table: str, tenant_column: str, company_column: str | None) -> None:
    """Activa RLS FORCE en `table` y crea la política de aislamiento (tenant + company opcional).

    `NULLIF(..., '')` hace que un contexto vacío (variable sin fijar o `''`) case a NULL y por tanto
    a 0 filas (falla cerrado), en vez de reventar el cast `''::uuid`. El `WITH CHECK` usa la MISMA
    expresión que el `USING`: sin eso, una escritura podría cruzar la frontera de company (una fila
    con `company_id` de otra empresa pasaría el check aunque el USING luego la ocultara).
    """
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    tenant_setting = "NULLIF(current_setting('app.tenant_id', true), '')"
    company_setting = "NULLIF(current_setting('app.company_id', true), '')"
    tenant_match = f"{tenant_column} = {tenant_setting}::uuid"
    if company_column is not None:
        company_match = (
            f"({company_setting} IS NULL OR {company_column} = {company_setting}::uuid)"
        )
        using = f"{tenant_match} AND {company_match}"
    else:
        using = tenant_match
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} "
        f"USING ({using}) WITH CHECK ({using})"
    )


def downgrade() -> None:
    for table in reversed(_BUSINESS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.drop_table("audit_log")
    op.drop_table("memberships")
    op.drop_table("companies")
    op.drop_table("users")
    op.drop_table("tenant_branding")
    op.drop_table("tenants")
    # El rol es a nivel de clúster; se deja (puede compartirse con otras BDs del mismo servidor).

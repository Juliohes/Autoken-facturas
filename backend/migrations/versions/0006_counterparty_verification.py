"""Verificación del CIF de contraparte (S2.8, ADR-0011): counterparties + cif_lookups + cif_sources.

Crea:
- `counterparties`: supplier master **por tenant** (RLS `FORCE` por `app.tenant_id`, patrón de
  `companies`/0001; tabla tenant-wide, sin `company_id`), UNIQUE `(tenant_id, cif)`, grants
  SELECT/INSERT/UPDATE al rol runtime. Lo que una asesoría confirma vale solo para ella.
- `cif_lookups`: caché **GLOBAL** de resoluciones de fuentes públicas, **SIN RLS de tenant** (no lleva
  `tenant_id` ni dato de negocio; excepción deliberada a la RLS de dos niveles, ADR-0011). Clave
  `(cif, source)`, grants SELECT/INSERT/UPDATE al rol runtime.
- `tenants.cif_sources` (JSONB, nullable): feature flags por tenant de las fuentes a consultar
  (`null` = conjunto por defecto).

Nota de aislamiento: el guard de arranque (`shared/db_security.py`, ADR-0014) solo marca tablas con
RLS habilitada pero SIN `FORCE`; una tabla SIN RLS como `cif_lookups` no lo activa, y el guard C8 de
`test_tenancy_rls` solo exige RLS a tablas con columna `tenant_id` (que `cif_lookups` no tiene). No
hace falta debilitar el guard ni ninguna allowlist: `cif_lookups` es pública global por diseño.

Revision ID: 0006_counterparty_verification
Revises: 0005_ocr_extractions
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_counterparty_verification"
down_revision = "0005_ocr_extractions"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    # --- Supplier master por tenant (`counterparties`) ------------------------------------------
    op.create_table(
        "counterparties",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cif", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("name_source", sa.Text(), nullable=False),
        sa.Column("times_seen", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "cif", name="counterparties_tenant_cif_unique"),
    )
    # El UNIQUE(tenant_id, cif) ya crea el índice btree que sirve la búsqueda de L2 (WHERE cif=...
    # acotado por tenant vía RLS): no hace falta un índice adicional.

    # RLS FORCE por tenant (patrón de `companies`/0001; tabla tenant-wide, sin segundo nivel por
    # empresa: el supplier master es de la asesoría entera). `NULLIF(..., '')` -> contexto vacío
    # case a 0 filas (fail-closed). `WITH CHECK` = `USING` para que ninguna escritura cruce el tenant.
    op.execute("ALTER TABLE counterparties ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE counterparties FORCE ROW LEVEL SECURITY")
    tenant_setting = "NULLIF(current_setting('app.tenant_id', true), '')"
    isolation = f"tenant_id = {tenant_setting}::uuid"
    op.execute(
        f"CREATE POLICY counterparties_tenant_isolation ON counterparties "
        f"USING ({isolation}) WITH CHECK ({isolation})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON counterparties TO {_APP_ROLE}")

    # --- Caché global de resoluciones (`cif_lookups`, SIN RLS de tenant) ------------------------
    # Clave natural `(cif, source)` como PK (da unicidad y PK a la vez). Sin `tenant_id`: es cache de
    # datos PÚBLICOS, compartida entre asesorías por diseño (ADR-0011). `exists` es palabra reservada
    # en SQL -> se declara entrecomillada.
    op.create_table(
        "cif_lookups",
        sa.Column("cif", sa.Text(), primary_key=True, nullable=False),
        sa.Column("source", sa.Text(), primary_key=True, nullable=False),
        sa.Column("exists", sa.Boolean(), nullable=False),
        sa.Column("official_name", sa.Text(), nullable=True),
        sa.Column("raw_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    # Las lecturas van siempre por la PK `(cif, source)` con filtro de vigencia (`expires_at > now()`):
    # el índice de la PK basta; no se añade un índice por `expires_at`.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON cif_lookups TO {_APP_ROLE}")

    # --- Feature flags por tenant (`tenants.cif_sources`) ---------------------------------------
    # JSONB nullable: `null` = conjunto por defecto (supplier_master + aeat + vies + borme). El rol
    # runtime ya tiene SELECT sobre `tenants` (0001), que cubre la columna nueva.
    op.add_column("tenants", sa.Column("cif_sources", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenants", "cif_sources")
    op.drop_table("cif_lookups")
    op.execute("DROP POLICY IF EXISTS counterparties_tenant_isolation ON counterparties")
    op.drop_table("counterparties")

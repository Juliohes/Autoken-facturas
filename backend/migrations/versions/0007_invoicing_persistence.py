"""Persistencia de la factura confirmada (S2.5, ADR-0001/0006/0011/0016): invoices + tramos + correcciones.

Crea las tres tablas del contexto `invoicing`, todas con RLS `FORCE` de DOS niveles por
`app.tenant_id` + `app.company_id` (mismo patrón que `companies`/0001, `uploaded_files`/0004 y
`ocr_extractions`/0005) y grants mínimos al rol runtime (SELECT/INSERT; sin UPDATE/DELETE: para
S2.5 la factura se crea y se lee, la edición auditada es S3.3):

- `invoices`: la factura contable persistida al confirmar. UNIQUE `(uploaded_file_id)` -> una factura
  por fichero (reconfirmar es 409, no duplica). Guarda el veredicto del CIF de contraparte
  (`counterparty_cif_status`, S2.8), el flag `is_test`, el aviso de descuadre (`balance_ok`) y el
  `snapshot` JSONB (datos confirmados + aceptación de responsabilidad) para la trazabilidad (§4).
- `invoice_tax_lines`: los tramos de IVA confirmados (un row por tramo del body).
- `ocr_corrections`: una fila por campo cuyo valor confirmado difiere del que persistió el OCR (S2.3);
  el dataset de mejora continua (§11.8 regla 13).

Registra los modelos ORM en `migrations/env.py` (`invoicing.models`); el guard `alembic check` de CI
detecta la deriva ORM<->migración.

Revision ID: 0007_invoicing_persistence
Revises: 0006_counterparty_verification
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_invoicing_persistence"
down_revision = "0006_counterparty_verification"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"

# RLS FORCE de dos niveles idéntica a `uploaded_files`/`ocr_extractions`: aislamiento por
# `app.tenant_id` + segundo nivel por `app.company_id`. `NULLIF(..., '')` -> contexto vacío case a 0
# filas (fail-closed); `company_id` sin fijar (asesoría del `tenant_admin`) deja ver/escribir todo el
# tenant. El `WITH CHECK` usa la MISMA expresión que el `USING` (ninguna fila cruza tenant ni empresa).
_TENANT_SETTING = "NULLIF(current_setting('app.tenant_id', true), '')"
_COMPANY_SETTING = "NULLIF(current_setting('app.company_id', true), '')"
_ISOLATION = (
    f"tenant_id = {_TENANT_SETTING}::uuid "
    f"AND ({_COMPANY_SETTING} IS NULL OR company_id = {_COMPANY_SETTING}::uuid)"
)


def _enable_two_level_rls(table: str) -> None:
    """Activa RLS FORCE de dos niveles y su política de aislamiento sobre `table`."""
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY {table}_tenant_isolation ON {table} "
        f"USING ({_ISOLATION}) WITH CHECK ({_ISOLATION})"
    )
    op.execute(f"GRANT SELECT, INSERT ON {table} TO {_APP_ROLE}")


def upgrade() -> None:
    # --- invoices --------------------------------------------------------------------------------
    op.create_table(
        "invoices",
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
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("counterparty_tax_id", sa.Text(), nullable=True),
        sa.Column("counterparty_name", sa.Text(), nullable=True),
        sa.Column("counterparty_cif_status", sa.Text(), nullable=False),
        sa.Column("net_amount", sa.Numeric(), nullable=True),
        sa.Column("tax_amount", sa.Numeric(), nullable=True),
        sa.Column("total_amount", sa.Numeric(), nullable=True),
        sa.Column("irpf_amount", sa.Numeric(), nullable=True),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # `balance_ok`: aviso de descuadre aritmético (regla 5). NULL = no comprobable (faltan
        # importes); no bloquea. La factura se guarda igual (el descuadre avisa, no bloquea).
        sa.Column("balance_ok", sa.Boolean(), nullable=True),
        # Snapshot append-only de lo confirmado (datos + aceptación de responsabilidad) para la
        # trazabilidad; se complementa con la entrada `invoice.confirm` en `audit_log`.
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "confirmed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("uploaded_file_id", name="invoices_uploaded_file_unique"),
    )
    _enable_two_level_rls("invoices")

    # --- invoice_tax_lines -----------------------------------------------------------------------
    op.create_table(
        "invoice_tax_lines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("iva_pct", sa.Numeric(), nullable=True),
        sa.Column("base", sa.Numeric(), nullable=True),
        sa.Column("cuota", sa.Numeric(), nullable=True),
    )
    _enable_two_level_rls("invoice_tax_lines")

    # --- ocr_corrections -------------------------------------------------------------------------
    op.create_table(
        "ocr_corrections",
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
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("ai_value", sa.Text(), nullable=True),
        sa.Column("human_value", sa.Text(), nullable=True),
        sa.Column(
            "corrected_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    _enable_two_level_rls("ocr_corrections")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ocr_corrections_tenant_isolation ON ocr_corrections")
    op.drop_table("ocr_corrections")
    op.execute("DROP POLICY IF EXISTS invoice_tax_lines_tenant_isolation ON invoice_tax_lines")
    op.drop_table("invoice_tax_lines")
    op.execute("DROP POLICY IF EXISTS invoices_tenant_isolation ON invoices")
    op.drop_table("invoices")

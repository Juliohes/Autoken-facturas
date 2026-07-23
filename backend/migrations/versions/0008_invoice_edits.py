"""Edición auditada de una factura confirmada (S3.3, ADR-0001): tabla `invoice_edits` + grants.

Hasta esta migración el rol runtime solo tenía `SELECT, INSERT` sobre `invoices`/`invoice_tax_lines`
(0007): "la factura se crea y se lee, la edición auditada es S3.3" (comentario original de la 0007).
Esta migración:

- Añade `UPDATE` sobre `invoices` (editar los campos, spec §2/§4) y `DELETE` sobre
  `invoice_tax_lines` (reemplazo completo del conjunto de tramos al editar, spec §2 C6). `INSERT` ya
  estaba concedido en ambas desde 0007; no se toca `ocr_extractions`/`ocr_corrections` (ajenas a esta
  tarea) ni `audit_log` (sigue append-only por diseño, 0001).
- Crea `invoice_edits`: una fila por CAMPO que cambió en una edición (no una fila por edición),
  mismo patrón de "diff" que `ocr_corrections` (0007) pero para ediciones humano-vs-humano
  post-confirmación (no IA-vs-humano en el momento de confirmar). RLS `FORCE` de dos niveles idéntica
  al resto del contexto; grants `SELECT, INSERT` (append-only, igual que `ocr_corrections`).

Revision ID: 0008_invoice_edits
Revises: 0007_invoicing_persistence
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_invoice_edits"
down_revision = "0007_invoicing_persistence"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"

# Misma expresión de aislamiento de dos niveles que 0007 (tenant_id + company_id opcional).
_TENANT_SETTING = "NULLIF(current_setting('app.tenant_id', true), '')"
_COMPANY_SETTING = "NULLIF(current_setting('app.company_id', true), '')"
_ISOLATION = (
    f"tenant_id = {_TENANT_SETTING}::uuid "
    f"AND ({_COMPANY_SETTING} IS NULL OR company_id = {_COMPANY_SETTING}::uuid)"
)


def upgrade() -> None:
    # --- grants: habilitar la edición sobre las tablas ya existentes (0007) ------------------------
    op.execute(f"GRANT UPDATE ON invoices TO {_APP_ROLE}")
    op.execute(f"GRANT DELETE ON invoice_tax_lines TO {_APP_ROLE}")

    # --- invoice_edits -----------------------------------------------------------------------------
    op.create_table(
        "invoice_edits",
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
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column(
            "edited_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "edited_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.execute("ALTER TABLE invoice_edits ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE invoice_edits FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY invoice_edits_tenant_isolation ON invoice_edits "
        f"USING ({_ISOLATION}) WITH CHECK ({_ISOLATION})"
    )
    op.execute(f"GRANT SELECT, INSERT ON invoice_edits TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS invoice_edits_tenant_isolation ON invoice_edits")
    op.drop_table("invoice_edits")
    op.execute(f"REVOKE DELETE ON invoice_tax_lines FROM {_APP_ROLE}")
    op.execute(f"REVOKE UPDATE ON invoices FROM {_APP_ROLE}")

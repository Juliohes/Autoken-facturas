"""Edición auditada de una empresa (2026-08-01, decisión de Julio: cada celda editable, con
historial permanente y posibilidad de revertir). Mismo patrón exacto que `invoice_edits` (S3.3,
migración 0008): una fila por CAMPO que cambió, RLS `FORCE` de dos niveles idéntica, grants
`SELECT, INSERT` (append-only — revertir es un nuevo `PATCH` con el valor antiguo, nunca un
`UPDATE`/`DELETE` sobre el historial en sí).

`name`/`cif` ya viven cifrados en `companies` (S5.2); sus valores en `company_edits.old_value`/
`new_value` se cifran igual (mismo mecanismo que `invoice_edits.old_value`/`new_value` para
`counterparty_tax_id`/`counterparty_name`, `pgp_sym_encrypt` ya concedido a `autoken_app` desde
0020). `notes`/`status` se guardan en claro, como siempre.

Hueco conocido, documentado no corregido (mismo criterio que S5.2 dejó con `ocr_comparison_runs`/
`ocr_ranking_entries`): `jobs/key_rotation.py` rota `invoice_edits` de forma explícita
(`_rotate_invoice_edits`) pero no conoce esta tabla nueva — una rotación de clave maestra dejaría
sin rotar el histórico cifrado de `company_edits`. No bloquea esta tarea (la rotación es un
procedimiento manual de emergencia, nunca ejecutado contra datos reales todavía); sí debe
resolverse antes de la primera rotación real.

Revision ID: 0026_company_edits
Revises: 0025_tenant_metrics_v2
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026_company_edits"
down_revision = "0025_tenant_metrics_v2"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"

# Misma expresión de aislamiento de dos niveles que `invoice_edits` (0008): tenant_id + company_id
# opcional (un `user` con sesión acotada a su empresa solo ve el historial de esa empresa).
_TENANT_SETTING = "NULLIF(current_setting('app.tenant_id', true), '')"
_COMPANY_SETTING = "NULLIF(current_setting('app.company_id', true), '')"
_ISOLATION = (
    f"tenant_id = {_TENANT_SETTING}::uuid "
    f"AND ({_COMPANY_SETTING} IS NULL OR company_id = {_COMPANY_SETTING}::uuid)"
)


def upgrade() -> None:
    op.create_table(
        "company_edits",
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
    op.create_index("ix_company_edits_company", "company_edits", ["company_id", "edited_at"])
    op.execute("ALTER TABLE company_edits ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE company_edits FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY company_edits_tenant_isolation ON company_edits "
        f"USING ({_ISOLATION}) WITH CHECK ({_ISOLATION})"
    )
    op.execute(f"GRANT SELECT, INSERT ON company_edits TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS company_edits_tenant_isolation ON company_edits")
    op.drop_table("company_edits")

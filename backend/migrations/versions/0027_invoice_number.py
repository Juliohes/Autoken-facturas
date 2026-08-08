"""Número de factura como campo de oro nuevo (S6.1, spec docs/specs/S6.1-rediseno-celdas-
comprobacion.md, decisión de Julio 2026-08-08): se lee por IA igual que fecha/total/CIF de
contraparte, no es manual como el IRPF.

`ocr_extractions.invoice_number`/`invoices.invoice_number`: texto plano, SIN cifrar (spec C7) —
mismo criterio que `total_amount`/`issue_date` (importes/fecha no cifran desde S5.2; solo el
CIF/nombre de contraparte, que sí son datos de identidad de la contraparte). Un número de factura no
identifica a una persona/entidad, es un dato interno de la propia factura.

Revision ID: 0027_invoice_number
Revises: 0026_company_edits
Create Date: 2026-08-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_invoice_number"
down_revision = "0026_company_edits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ocr_extractions", sa.Column("invoice_number", sa.Text(), nullable=True))
    op.add_column("invoices", sa.Column("invoice_number", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "invoice_number")
    op.drop_column("ocr_extractions", "invoice_number")

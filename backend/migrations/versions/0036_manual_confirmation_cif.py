"""Persiste la alerta de CIF propio ausente confirmada en S6.10.

La alerta es un snapshot de la decisión de confirmación: no se recalcula si se reprocesa el OCR o
cambia después el CIF de la empresa. El segundo campo deja trazabilidad de que un `user` aceptó la
excepción expresamente; un administrador puede confirmar la misma situación sin esa aceptación.

Revision ID: 0036_manual_confirmation_cif
Revises: 0035_benchmark_retry_safety
Create Date: 2026-08-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_manual_confirmation_cif"
down_revision = "0035_benchmark_retry_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invoices",
        sa.Column("own_tax_id_missing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "invoices",
        sa.Column(
            "own_tax_id_exception_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # No hay una prueba histórica inmutable de si el CIF propio se vio al confirmar: la extracción
    # OCR se puede sobrescribir al reprocesar. Las facturas previas quedan sin alerta para no mentir;
    # desde esta migración el hecho se captura en `invoices` dentro de la confirmación atómica.
    op.create_index(
        "invoices_own_tax_id_missing_idx",
        "invoices",
        ["tenant_id", sa.text("confirmed_at DESC"), sa.text("id DESC")],
        postgresql_where=sa.text("own_tax_id_missing = true AND is_test = false"),
    )
    op.create_check_constraint(
        "invoices_own_tax_id_exception_requires_missing",
        "invoices",
        "NOT own_tax_id_exception_confirmed OR own_tax_id_missing",
    )


def downgrade() -> None:
    op.drop_constraint("invoices_own_tax_id_exception_requires_missing", "invoices")
    op.drop_index("invoices_own_tax_id_missing_idx", table_name="invoices")
    op.drop_column("invoices", "own_tax_id_exception_confirmed")
    op.drop_column("invoices", "own_tax_id_missing")

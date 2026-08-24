"""Agrupación UX opcional para captura continua (R-013)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0054_r013_capture_session"
down_revision = "0053_r051_supplier_profile_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "uploaded_files",
        sa.Column("capture_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "uploaded_files",
        sa.Column("capture_sequence", sa.SmallInteger(), nullable=True),
    )
    op.create_check_constraint(
        "uploaded_files_capture_session_check",
        "uploaded_files",
        "((capture_session_id IS NULL AND capture_sequence IS NULL) OR "
        "(capture_session_id IS NOT NULL AND capture_sequence BETWEEN 1 AND 50))",
    )
    op.create_index(
        "ix_uploaded_files_capture_session",
        "uploaded_files",
        ["tenant_id", "uploaded_by", "capture_session_id", "capture_sequence"],
        postgresql_where=sa.text("capture_session_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_uploaded_files_capture_session", table_name="uploaded_files")
    op.drop_constraint("uploaded_files_capture_session_check", "uploaded_files", type_="check")
    op.drop_column("uploaded_files", "capture_sequence")
    op.drop_column("uploaded_files", "capture_session_id")

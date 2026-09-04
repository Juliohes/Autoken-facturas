"""Progreso durable del OCR separado de su estado final (R-016/R-017)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_processing_stage"
down_revision = "0040_ocr_irpf_fields"
branch_labels = None
depends_on = None

_STAGES = (
    "'queued', 'loading_document', 'primary_ocr', 'validating', 'fallback_ocr', "
    "'consensus', 'persisting'"
)
_APP_ROLE = "autoken_app"


def upgrade() -> None:
    op.add_column("uploaded_files", sa.Column("processing_stage", sa.Text(), nullable=True))
    op.add_column(
        "uploaded_files", sa.Column("ocr_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "uploaded_files", sa.Column("ocr_finished_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("UPDATE uploaded_files SET processing_stage = 'queued' WHERE status = 'pending_ocr'")
    op.alter_column(
        "uploaded_files",
        "processing_stage",
        server_default=sa.text("'queued'"),
    )
    op.create_check_constraint(
        "uploaded_files_processing_stage_check",
        "uploaded_files",
        f"processing_stage IS NULL OR processing_stage IN ({_STAGES})",
    )
    op.execute(
        f"GRANT UPDATE (processing_stage, ocr_started_at, ocr_finished_at) "
        f"ON uploaded_files TO {_APP_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        f"REVOKE UPDATE (processing_stage, ocr_started_at, ocr_finished_at) "
        f"ON uploaded_files FROM {_APP_ROLE}"
    )
    op.drop_constraint("uploaded_files_processing_stage_check", "uploaded_files", type_="check")
    op.drop_column("uploaded_files", "ocr_finished_at")
    op.drop_column("uploaded_files", "ocr_started_at")
    op.drop_column("uploaded_files", "processing_stage")

"""Metadatos de trazabilidad para aperturas globales auditadas (R-027)."""

from alembic import op
import sqlalchemy as sa

revision = "0043_audit_request_metadata"
down_revision = "0042_review_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audit_log", sa.Column("request_id", sa.Text(), nullable=True))
    op.add_column("audit_log", sa.Column("source_ip", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("audit_log", "source_ip")
    op.drop_column("audit_log", "request_id")

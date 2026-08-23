"""Contadores acumulativos de la purga de documentos no confirmados (R-028)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_retention_metrics"
down_revision = "0043_audit_request_metadata"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    op.create_table(
        "retention_metrics",
        sa.Column("id", sa.Boolean(), primary_key=True, server_default=sa.text("true")),
        sa.Column("expired_pending_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("purge_storage_failures", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("id", name="retention_metrics_singleton_check"),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON retention_metrics TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE SELECT, INSERT, UPDATE ON retention_metrics FROM {_APP_ROLE}")
    op.drop_table("retention_metrics")

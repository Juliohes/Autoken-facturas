"""Borradores editables de revisión, separados de la factura confirmada (R-021)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0042_review_drafts"
down_revision = "0041_processing_stage"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_TENANT_SETTING = "NULLIF(current_setting('app.tenant_id', true), '')"
_COMPANY_SETTING = "NULLIF(current_setting('app.company_id', true), '')"
_ISOLATION = (
    f"tenant_id = {_TENANT_SETTING}::uuid "
    f"AND ({_COMPANY_SETTING} IS NULL OR company_id = {_COMPANY_SETTING}::uuid)"
)


def upgrade() -> None:
    op.create_table(
        "review_drafts",
        sa.Column(
            "uploaded_file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
            primary_key=True,
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
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("invoice_number", sa.Text(), nullable=True),
        sa.Column("counterparty_tax_id", postgresql.BYTEA(), nullable=True),
        sa.Column("counterparty_tax_id_blind_index", sa.Text(), nullable=True),
        sa.Column("counterparty_name", postgresql.BYTEA(), nullable=True),
        sa.Column("net_amount", sa.Numeric(), nullable=True),
        sa.Column("tax_amount", sa.Numeric(), nullable=True),
        sa.Column("total_amount", sa.Numeric(), nullable=True),
        sa.Column("irpf_amount", sa.Numeric(), nullable=True),
        sa.Column(
            "tax_lines",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "direction IS NULL OR direction IN ('recibida', 'emitida')",
            name="review_drafts_direction_check",
        ),
        sa.Index("ix_review_drafts_owner_updated", "owner_user_id", "updated_at"),
    )
    op.execute("ALTER TABLE review_drafts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE review_drafts FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY review_drafts_tenant_isolation ON review_drafts "
        f"USING ({_ISOLATION}) WITH CHECK ({_ISOLATION})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON review_drafts TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON review_drafts FROM {_APP_ROLE}")
    op.execute("DROP POLICY review_drafts_tenant_isolation ON review_drafts")
    op.drop_table("review_drafts")

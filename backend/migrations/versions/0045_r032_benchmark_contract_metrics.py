"""Metadatos y métricas del benchmark comparable R-032."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0045_r032_contract_metrics"
down_revision = "0044_retention_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ocr_benchmark_results", sa.Column("benchmark_contract_version", sa.Text()))
    op.add_column("ocr_benchmark_results", sa.Column("schema_version", sa.Text()))
    op.add_column("ocr_benchmark_results", sa.Column("normalization_version", sa.Text()))
    op.add_column("ocr_benchmark_results", sa.Column("ground_truth_hash", sa.Text()))
    op.add_column("ocr_benchmark_results", sa.Column("document_sha256", sa.Text()))
    op.add_column("ocr_benchmark_results", sa.Column("variant_sha256", sa.Text()))
    op.add_column("ocr_benchmark_results", sa.Column("pages", sa.Integer()))
    op.add_column(
        "ocr_benchmark_results",
        sa.Column("field_exact_accuracy", sa.Float(), nullable=True),
    )
    op.add_column(
        "ocr_benchmark_results",
        sa.Column("critical_field_accuracy", sa.Float(), nullable=True),
    )
    op.add_column(
        "ocr_benchmark_results",
        sa.Column("all_critical_exact", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "ocr_benchmark_results", sa.Column("arithmetic_valid", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "ocr_benchmark_results",
        sa.Column("hallucination_flags", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "ocr_benchmark_results",
        sa.Column("manual_corrections_per_invoice", sa.Integer(), nullable=True),
    )
    op.add_column("ocr_benchmark_results", sa.Column("api_cost_usd", sa.Numeric(12, 8)))


def downgrade() -> None:
    for name in (
        "api_cost_usd",
        "manual_corrections_per_invoice",
        "hallucination_flags",
        "arithmetic_valid",
        "all_critical_exact",
        "critical_field_accuracy",
        "field_exact_accuracy",
        "pages",
        "variant_sha256",
        "document_sha256",
        "ground_truth_hash",
        "normalization_version",
        "schema_version",
        "benchmark_contract_version",
    ):
        op.drop_column("ocr_benchmark_results", name)

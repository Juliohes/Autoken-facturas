"""Añade el contador durable de documentos listos para la telemetría R-047."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0051_r047_telemetry"
down_revision = "0050_r046_ocr_lab_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ocr_recovery_metrics",
        sa.Column("ready", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.ocr_recovery_candidates(p_limit integer)
        RETURNS TABLE(tenant_id uuid, company_id uuid, uploaded_file_id uuid)
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            INSERT INTO public.ocr_recovery_metrics
                (id, pending, processing, abandoned, failed, ready, observed_at)
            SELECT true,
                   count(*) FILTER (WHERE status = 'pending_ocr'),
                   count(*) FILTER (WHERE status = 'processing' AND ocr_claim_expires_at >= now()),
                   count(*) FILTER (WHERE status = 'processing' AND ocr_claim_expires_at < now()),
                   count(*) FILTER (WHERE status = 'ocr_failed'),
                   count(*) FILTER (WHERE status IN ('ocr_done', 'needs_review')),
                   now()
            FROM public.uploaded_files
            ON CONFLICT (id) DO UPDATE SET
                pending = EXCLUDED.pending,
                processing = EXCLUDED.processing,
                abandoned = EXCLUDED.abandoned,
                failed = EXCLUDED.failed,
                ready = EXCLUDED.ready,
                observed_at = EXCLUDED.observed_at;

            RETURN QUERY
            WITH candidates AS (
                SELECT f.id
                FROM public.uploaded_files f
                WHERE (f.status = 'pending_ocr'
                       OR (f.status = 'processing' AND f.ocr_claim_expires_at < now()))
                  AND (f.ocr_recovery_enqueued_at IS NULL
                       OR f.ocr_recovery_enqueued_at < now() - interval '5 minutes')
                ORDER BY f.created_at
                LIMIT p_limit
                FOR UPDATE SKIP LOCKED
            )
            UPDATE public.uploaded_files f
            SET ocr_recovery_enqueued_at = now()
            FROM candidates c
            WHERE f.id = c.id
            RETURNING f.tenant_id, f.company_id, f.id;
        END;
        $$
        """
    )


def downgrade() -> None:
    op.drop_column("ocr_recovery_metrics", "ready")

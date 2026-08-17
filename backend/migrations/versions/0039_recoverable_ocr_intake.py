"""OCR recuperable y dirección durable de captura (S6.13).

El claim vive junto al documento, que es la fuente durable incluso si Redis o un worker se reinician.
La función SECURITY DEFINER solo expone al runtime identificadores internos necesarios para reencolar
y escribe una instantánea global de contadores, sin datos de facturas ni de usuarios.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0039_recoverable_ocr_intake"
down_revision = "0038_private_upload_dedup"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.add_column("uploaded_files", sa.Column("direction", sa.Text(), nullable=True))
    op.add_column(
        "uploaded_files", sa.Column("ocr_claim_token", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "uploaded_files", sa.Column("ocr_claim_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "uploaded_files", sa.Column("ocr_recovery_enqueued_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "uploaded_files_direction_check",
        "uploaded_files",
        "direction IS NULL OR direction IN ('recibida', 'emitida')",
    )
    op.create_index(
        "ix_uploaded_files_ocr_recovery",
        "uploaded_files",
        ["status", "ocr_claim_expires_at", "ocr_recovery_enqueued_at"],
    )
    op.execute(
        f"GRANT UPDATE (status, ocr_claim_token, ocr_claim_expires_at, ocr_recovery_enqueued_at) ON uploaded_files TO {_APP_ROLE}"
    )

    op.create_table(
        "ocr_recovery_metrics",
        sa.Column("id", sa.Boolean(), primary_key=True, server_default=sa.text("true")),
        sa.Column("pending", sa.BigInteger(), nullable=False),
        sa.Column("processing", sa.BigInteger(), nullable=False),
        sa.Column("abandoned", sa.BigInteger(), nullable=False),
        sa.Column("failed", sa.BigInteger(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("id", name="ocr_recovery_metrics_singleton_check"),
    )

    op.execute(
        """
        CREATE FUNCTION public.ocr_recovery_candidates(p_limit integer)
        RETURNS TABLE(tenant_id uuid, company_id uuid, uploaded_file_id uuid)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            INSERT INTO public.ocr_recovery_metrics (id, pending, processing, abandoned, failed, observed_at)
            SELECT true,
                   count(*) FILTER (WHERE status = 'pending_ocr'),
                   count(*) FILTER (WHERE status = 'processing' AND ocr_claim_expires_at >= now()),
                   count(*) FILTER (WHERE status = 'processing' AND ocr_claim_expires_at < now()),
                   count(*) FILTER (WHERE status = 'ocr_failed'),
                   now()
            FROM public.uploaded_files
            ON CONFLICT (id) DO UPDATE SET
                pending = EXCLUDED.pending,
                processing = EXCLUDED.processing,
                abandoned = EXCLUDED.abandoned,
                failed = EXCLUDED.failed,
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
    op.execute("ALTER FUNCTION public.ocr_recovery_candidates(integer) OWNER TO " + _DEFINER_ROLE)
    op.execute("REVOKE ALL ON FUNCTION public.ocr_recovery_candidates(integer) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.ocr_recovery_candidates(integer) TO {_APP_ROLE}")
    op.execute(f"GRANT SELECT, UPDATE (ocr_recovery_enqueued_at) ON public.uploaded_files TO {_DEFINER_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON public.ocr_recovery_metrics TO {_DEFINER_ROLE}")
    op.execute(f"GRANT SELECT ON ocr_recovery_metrics TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE SELECT ON ocr_recovery_metrics FROM {_APP_ROLE}")
    op.execute(f"REVOKE EXECUTE ON FUNCTION public.ocr_recovery_candidates(integer) FROM {_APP_ROLE}")
    op.execute("DROP FUNCTION IF EXISTS public.ocr_recovery_candidates(integer)")
    op.drop_table("ocr_recovery_metrics")
    op.execute(
        f"REVOKE UPDATE (ocr_claim_token, ocr_claim_expires_at, ocr_recovery_enqueued_at) ON uploaded_files FROM {_APP_ROLE}"
    )
    op.drop_index("ix_uploaded_files_ocr_recovery", table_name="uploaded_files")
    op.drop_constraint("uploaded_files_direction_check", "uploaded_files", type_="check")
    op.drop_column("uploaded_files", "ocr_claim_expires_at")
    op.drop_column("uploaded_files", "ocr_claim_token")
    op.drop_column("uploaded_files", "ocr_recovery_enqueued_at")
    op.drop_column("uploaded_files", "direction")

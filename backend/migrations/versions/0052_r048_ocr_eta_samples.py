"""Muestras agregadas para estimar ETA de OCR sin PII (R-048)."""

from __future__ import annotations

from alembic import op


revision = "0052_r048_ocr_eta_samples"
down_revision = "0051_r047_telemetry"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.ocr_processing_samples (
            id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            engine text NOT NULL,
            model text NOT NULL,
            page_count_bucket text NOT NULL CHECK (page_count_bucket IN ('1', '2-5', '6-10', '11+')),
            status text NOT NULL,
            queue_wait_seconds double precision NOT NULL CHECK (queue_wait_seconds >= 0),
            processing_seconds double precision NOT NULL CHECK (processing_seconds >= 0),
            completed_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_ocr_processing_samples_lookup
        ON public.ocr_processing_samples (engine, model, page_count_bucket, completed_at DESC)
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.record_ocr_processing_sample(
            p_engine text,
            p_model text,
            p_page_count_bucket text,
            p_status text,
            p_queue_wait_seconds double precision,
            p_processing_seconds double precision
        ) RETURNS void
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            INSERT INTO public.ocr_processing_samples
                (engine, model, page_count_bucket, status, queue_wait_seconds, processing_seconds)
            VALUES
                (p_engine, p_model, p_page_count_bucket, p_status,
                 p_queue_wait_seconds, p_processing_seconds);
            DELETE FROM public.ocr_processing_samples
            WHERE completed_at < now() - interval '30 days';
        END;
        $$
        """
    )
    op.execute(
        "ALTER FUNCTION public.record_ocr_processing_sample(text, text, text, text, double precision, double precision) "
        f"OWNER TO {_DEFINER_ROLE}"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.record_ocr_processing_sample(text, text, text, text, double precision, double precision) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.record_ocr_processing_sample(text, text, text, text, double precision, double precision) "
        f"TO {_APP_ROLE}"
    )
    op.execute("GRANT SELECT ON public.ocr_processing_samples TO autoken_app")


def downgrade() -> None:
    op.execute(
        "REVOKE EXECUTE ON FUNCTION public.record_ocr_processing_sample(text, text, text, text, double precision, double precision) FROM autoken_app"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS public.record_ocr_processing_sample(text, text, text, text, double precision, double precision)"
    )
    op.execute("DROP INDEX IF EXISTS public.ix_ocr_processing_samples_lookup")
    op.execute("DROP TABLE IF EXISTS public.ocr_processing_samples")

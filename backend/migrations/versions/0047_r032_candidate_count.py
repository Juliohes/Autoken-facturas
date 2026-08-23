"""Ajusta el descubrimiento de lotes al denominador de cuatro candidatos R-032."""

from __future__ import annotations

from alembic import op

revision = "0047_r032_candidate_count"
down_revision = "0046_r032_metrics_summary"
branch_labels = None
depends_on = None

_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.ocr_benchmark_candidates(p_limit integer)
        RETURNS TABLE (tenant_id uuid, company_id uuid, uploaded_file_id uuid)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT i.tenant_id, i.company_id, i.uploaded_file_id
            FROM public.invoices i
            LEFT JOIN (
                SELECT uploaded_file_id, COUNT(*) AS combinations
                FROM public.ocr_benchmark_results
                GROUP BY uploaded_file_id
            ) b ON b.uploaded_file_id = i.uploaded_file_id
            WHERE i.is_test = false
              AND COALESCE(b.combinations, 0) < 12
            ORDER BY i.confirmed_at DESC
            LIMIT p_limit
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION public.ocr_benchmark_candidates(integer) OWNER TO {_DEFINER_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.ocr_benchmark_candidates(p_limit integer)
        RETURNS TABLE (tenant_id uuid, company_id uuid, uploaded_file_id uuid)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT i.tenant_id, i.company_id, i.uploaded_file_id
            FROM public.invoices i
            LEFT JOIN (
                SELECT uploaded_file_id, COUNT(*) AS combinations
                FROM public.ocr_benchmark_results
                GROUP BY uploaded_file_id
            ) b ON b.uploaded_file_id = i.uploaded_file_id
            WHERE i.is_test = false
              AND COALESCE(b.combinations, 0) < 18
            ORDER BY i.confirmed_at DESC
            LIMIT p_limit
        $$;
        """
    )

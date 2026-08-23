"""Informe agregado de métricas R-032 por variante, motor y modelo."""

from __future__ import annotations

from alembic import op

revision = "0046_r032_metrics_summary"
down_revision = "0045_r032_contract_metrics"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(
        f"""
        GRANT SELECT (
            variant, engine, model, error, field_exact_accuracy, critical_field_accuracy,
            all_critical_exact, tax_lines_matched, arithmetic_valid, hallucination_flags,
            duration_ms, pages, api_cost_usd, manual_corrections_per_invoice
        ) ON public.ocr_benchmark_results TO {_DEFINER_ROLE}
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.ocr_benchmark_r032_metrics_summary()
        RETURNS TABLE (
            variant text,
            engine text,
            model text,
            executions bigint,
            errors bigint,
            field_exact_accuracy double precision,
            critical_field_accuracy double precision,
            all_critical_exact_rate double precision,
            tax_lines_accuracy double precision,
            arithmetic_valid_rate double precision,
            hallucination_cases bigint,
            p50_duration_ms double precision,
            p95_duration_ms double precision,
            pages double precision,
            api_cost_usd numeric,
            manual_corrections_per_invoice double precision
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT
                variant,
                engine,
                model,
                COUNT(*) AS executions,
                COUNT(*) FILTER (WHERE error IS NOT NULL) AS errors,
                AVG(field_exact_accuracy) FILTER (WHERE error IS NULL),
                AVG(critical_field_accuracy) FILTER (WHERE error IS NULL),
                AVG((all_critical_exact)::int::double precision)
                    FILTER (WHERE error IS NULL AND all_critical_exact IS NOT NULL),
                AVG((tax_lines_matched)::int::double precision)
                    FILTER (WHERE error IS NULL AND tax_lines_matched IS NOT NULL),
                AVG((arithmetic_valid)::int::double precision)
                    FILTER (WHERE error IS NULL AND arithmetic_valid IS NOT NULL),
                COUNT(*) FILTER (
                    WHERE error IS NULL
                      AND jsonb_array_length(COALESCE(hallucination_flags, '[]'::jsonb)) > 0
                ),
                percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms)
                    FILTER (WHERE error IS NULL AND duration_ms IS NOT NULL),
                percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)
                    FILTER (WHERE error IS NULL AND duration_ms IS NOT NULL),
                AVG(pages),
                SUM(api_cost_usd) FILTER (WHERE error IS NULL),
                AVG(manual_corrections_per_invoice) FILTER (WHERE error IS NULL)
            FROM public.ocr_benchmark_results
            GROUP BY variant, engine, model
            ORDER BY variant, engine, model
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION public.ocr_benchmark_r032_metrics_summary() OWNER TO {_DEFINER_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION public.ocr_benchmark_r032_metrics_summary() FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.ocr_benchmark_r032_metrics_summary() TO {_APP_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.ocr_benchmark_r032_metrics_summary()")
    op.execute(
        f"REVOKE SELECT (variant, engine, model, error, field_exact_accuracy, "
        f"critical_field_accuracy, all_critical_exact, tax_lines_matched, arithmetic_valid, "
        f"hallucination_flags, duration_ms, pages, api_cost_usd, manual_corrections_per_invoice) "
        f"ON public.ocr_benchmark_results FROM {_DEFINER_ROLE}"
    )

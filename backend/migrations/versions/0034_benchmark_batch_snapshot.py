"""Hace atómico el arranque del lote S6.7 y persiste su snapshot de candidatos.

La API no puede separar ``get_running`` de insertar el lote: dos peticiones concurrentes podían
ver ``None`` e insertar dos filas. Tampoco debe el worker redescubrir candidatos, porque el conjunto
podía cambiar entre el botón y su ejecución. La función toma un advisory xact lock y copia los
candidatos en una sola transacción SECURITY DEFINER.

Revision ID: 0034_benchmark_batch_snapshot
Revises: 0033_encrypt_ocr_experiment_pii
Create Date: 2026-08-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0034_benchmark_batch_snapshot"
down_revision = "0033_encrypt_ocr_experiment_pii"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"
_LOCK_KEY = 892_374_651_029_385
_ROW_COLUMNS = "id, status, total, completed, failed_count"
_ROW_TABLE_SPEC = "id uuid, status text, total integer, completed integer, failed_count integer"


def upgrade() -> None:
    op.create_table(
        "ocr_benchmark_batch_candidates",
        sa.Column(
            "batch_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ocr_benchmark_batch_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("batch_run_id", "uploaded_file_id"),
    )
    op.execute(
        f"GRANT SELECT, INSERT ON public.ocr_benchmark_batch_candidates TO {_DEFINER_ROLE}"
    )
    # El snapshot guarda IDs de tenant: aunque `autoken_app` no recibe ningún GRANT directo, RLS
    # forzada fail-closed evita que un permiso futuro exponga candidatos de otros tenants.
    op.execute("ALTER TABLE ocr_benchmark_batch_candidates ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ocr_benchmark_batch_candidates FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY ocr_benchmark_batch_candidates_no_direct_access "
        "ON ocr_benchmark_batch_candidates USING (false) WITH CHECK (false)"
    )
    op.execute(
        f"""
        CREATE FUNCTION public.start_benchmark_batch(p_limit integer)
        RETURNS TABLE (started boolean, {_ROW_TABLE_SPEC})
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
            v_id uuid;
        BEGIN
            PERFORM pg_advisory_xact_lock({_LOCK_KEY});
            RETURN QUERY
                SELECT false, b.id, b.status, b.total, b.completed, b.failed_count
                FROM public.ocr_benchmark_batch_runs AS b
                WHERE b.status = 'running'
                ORDER BY b.started_at DESC
                LIMIT 1;
            IF FOUND THEN
                RETURN;
            END IF;

            INSERT INTO public.ocr_benchmark_batch_runs (status, total)
            VALUES ('running', 0)
            RETURNING ocr_benchmark_batch_runs.id INTO v_id;

            INSERT INTO public.ocr_benchmark_batch_candidates
                (batch_run_id, tenant_id, company_id, uploaded_file_id)
            SELECT v_id, i.tenant_id, i.company_id, i.uploaded_file_id
            FROM public.invoices i
            LEFT JOIN (
                SELECT uploaded_file_id, COUNT(*) AS combinations
                FROM public.ocr_benchmark_results
                GROUP BY uploaded_file_id
            ) b ON b.uploaded_file_id = i.uploaded_file_id
            WHERE i.is_test = false
              AND COALESCE(b.combinations, 0) < 18
            ORDER BY i.confirmed_at DESC
            LIMIT LEAST(GREATEST(p_limit, 1), 30);

            UPDATE public.ocr_benchmark_batch_runs
            SET total = (SELECT COUNT(*) FROM public.ocr_benchmark_batch_candidates
                         WHERE batch_run_id = v_id)
            WHERE ocr_benchmark_batch_runs.id = v_id;

            RETURN QUERY
                SELECT true, b.id, b.status, b.total, b.completed, b.failed_count
                FROM public.ocr_benchmark_batch_runs AS b WHERE b.id = v_id;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.start_benchmark_batch(integer) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.start_benchmark_batch(integer) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.start_benchmark_batch(integer) TO {_APP_ROLE}")
    op.execute(
        """
        CREATE FUNCTION public.get_benchmark_batch_candidates(p_batch_run_id uuid)
        RETURNS TABLE (tenant_id uuid, company_id uuid, uploaded_file_id uuid)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT tenant_id, company_id, uploaded_file_id
            FROM public.ocr_benchmark_batch_candidates
            WHERE batch_run_id = p_batch_run_id
            ORDER BY uploaded_file_id
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION public.get_benchmark_batch_candidates(uuid) OWNER TO {_DEFINER_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION public.get_benchmark_batch_candidates(uuid) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.get_benchmark_batch_candidates(uuid) TO {_APP_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.get_benchmark_batch_candidates(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.start_benchmark_batch(integer)")
    op.execute(
        "DROP POLICY IF EXISTS ocr_benchmark_batch_candidates_no_direct_access "
        "ON ocr_benchmark_batch_candidates"
    )
    op.execute(f"REVOKE ALL ON public.ocr_benchmark_batch_candidates FROM {_DEFINER_ROLE}")
    op.drop_table("ocr_benchmark_batch_candidates")

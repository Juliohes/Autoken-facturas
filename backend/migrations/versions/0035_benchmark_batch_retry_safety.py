"""Impide que un redelivery de ARQ infle el progreso de un lote S6.7 ya cerrado.

Revision ID: 0035_benchmark_retry_safety
Revises: 0034_benchmark_batch_snapshot
Create Date: 2026-08-12
"""

from alembic import op

revision = "0035_benchmark_retry_safety"
down_revision = "0034_benchmark_batch_snapshot"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    # Un mensaje redelivered solo puede avanzar un lote activo y nunca más allá de su snapshot.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.advance_batch_run_progress(p_id uuid, p_failed boolean)
        RETURNS void
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            UPDATE public.ocr_benchmark_batch_runs
            SET completed = completed + 1,
                failed_count = failed_count + CASE WHEN p_failed THEN 1 ELSE 0 END
            WHERE id = p_id AND status = 'running' AND completed < total
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.advance_batch_run_progress(uuid, boolean) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.advance_batch_run_progress(uuid, boolean) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.advance_batch_run_progress(uuid, boolean) TO {_APP_ROLE}")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.finish_batch_run(p_id uuid, p_status text)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            IF p_status = 'done' THEN
                UPDATE public.ocr_benchmark_batch_runs
                    SET status = 'done', finished_at = now()
                    WHERE id = p_id AND status = 'running';
            ELSIF p_status = 'failed' THEN
                UPDATE public.ocr_benchmark_batch_runs
                    SET status = 'failed', finished_at = now()
                    WHERE id = p_id AND status = 'running';
            ELSE
                RAISE EXCEPTION 'finish_batch_run: estado no soportado %', p_status;
            END IF;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.finish_batch_run(uuid, text) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.finish_batch_run(uuid, text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.finish_batch_run(uuid, text) TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.advance_batch_run_progress(p_id uuid, p_failed boolean)
        RETURNS void
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            UPDATE public.ocr_benchmark_batch_runs
            SET completed = completed + 1,
                failed_count = failed_count + CASE WHEN p_failed THEN 1 ELSE 0 END
            WHERE id = p_id
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.advance_batch_run_progress(uuid, boolean) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.advance_batch_run_progress(uuid, boolean) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.advance_batch_run_progress(uuid, boolean) TO {_APP_ROLE}")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.finish_batch_run(p_id uuid, p_status text)
        RETURNS void
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            IF p_status = 'done' THEN
                UPDATE public.ocr_benchmark_batch_runs
                    SET status = 'done', finished_at = now()
                    WHERE id = p_id;
            ELSIF p_status = 'failed' THEN
                UPDATE public.ocr_benchmark_batch_runs
                    SET status = 'failed', finished_at = now()
                    WHERE id = p_id AND status = 'running';
            ELSE
                RAISE EXCEPTION 'finish_batch_run: estado no soportado %', p_status;
            END IF;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.finish_batch_run(uuid, text) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.finish_batch_run(uuid, text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.finish_batch_run(uuid, text) TO {_APP_ROLE}")

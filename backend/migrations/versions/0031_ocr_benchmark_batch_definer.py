"""Sustituye el `GRANT` directo a `autoken_app` sobre `ocr_benchmark_batch_runs` (migración 0030)
por funciones `SECURITY DEFINER` de superficie fija (S6.7 Área C, spec
docs/specs/S6.7-benchmark-real-motor-variante.md §0.5).

Hallazgo de auditoría (2026-08-11, coherencia con el precedente ya sentado por `platform_settings`,
migración 0017 -- el único precedente comparable de tabla de plataforma sin `tenant_id`/RLS):
`platform_settings` decidió DELIBERADAMENTE no conceder acceso directo al rol runtime, solo a través
de `get_platform_settings()`/`set_platform_settings()`. La migración 0030 rompió ese patrón,
concediendo `SELECT, INSERT, UPDATE` directo a `autoken_app` sobre `ocr_benchmark_batch_runs` --
primera tabla de plataforma del proyecto alcanzable con SQL arbitrario desde el rol compartido
(cualquier sesión con ese rol, incluida una `tenant_session`, podía tocarla, sin RLS que lo
impidiera). No es una fuga de datos de tenant (la tabla no tiene ninguno), pero rompe la defensa en
profundidad ya establecida.

Esta migración revoca ese `GRANT` directo y lo sustituye por 6 funciones `SECURITY DEFINER`, mismo
patrón que 0017/0019/0028/0030 (owner `autoken_definer`, `SET search_path = pg_catalog, pg_temp`,
`REVOKE ALL FROM PUBLIC` + `GRANT EXECUTE TO autoken_app`), cubriendo exactamente la superficie que
hoy usan `platform_admin.benchmark_batch_repository`/`jobs.ocr_benchmark_batch`:

- `get_running_batch_run()`: el lote `running` más reciente, o ninguna fila (C11/C16).
- `get_latest_batch_run()`: el lote más reciente, cualquier estado, o ninguna fila (C16).
- `get_batch_run(p_id)`: un lote por id (usado por `_discover_and_run` para leer su `total`).
- `insert_running_batch_run(p_total)`: inserta un lote nuevo en `running` (C10).
- `advance_batch_run_progress(p_id, p_failed)`: avanza `completed`/`failed_count` en un solo UPDATE
  (C13), sin `RETURNING` (el llamador no lo necesita).
- `finish_batch_run(p_id, p_status)`: cierra el lote -- `p_status='done'` incondicional (mismo
  criterio que el `_mark_done` original); `p_status='failed'` SOLO si sigue `running` (mismo
  criterio que el `_mark_failed` original: si el bucle por candidato ya lo dejó `done`, no lo pisa
  hacia atrás).

Revision ID: 0031_ocr_benchmark_batch_definer
Revises: 0030_ocr_benchmark_batch_runs
Create Date: 2026-08-11
"""

from __future__ import annotations

from alembic import op

revision = "0031_ocr_benchmark_batch_definer"
down_revision = "0030_ocr_benchmark_batch_runs"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"

_ROW_COLUMNS = "id, status, total, completed, failed_count"
_ROW_TABLE_SPEC = (
    "id uuid, status text, total integer, completed integer, failed_count integer"
)


def upgrade() -> None:
    # Retira el acceso directo concedido por 0030; el rol runtime solo puede tocar la tabla a
    # través de las funciones `SECURITY DEFINER` de abajo (mismo patrón que `platform_settings`).
    op.execute(f"REVOKE SELECT, INSERT, UPDATE ON public.ocr_benchmark_batch_runs FROM {_APP_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON public.ocr_benchmark_batch_runs TO {_DEFINER_ROLE}"
    )

    op.execute(
        f"""
        CREATE FUNCTION public.get_running_batch_run()
        RETURNS TABLE ({_ROW_TABLE_SPEC})
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT {_ROW_COLUMNS} FROM public.ocr_benchmark_batch_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.get_running_batch_run() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.get_running_batch_run() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.get_running_batch_run() TO {_APP_ROLE}")

    op.execute(
        f"""
        CREATE FUNCTION public.get_latest_batch_run()
        RETURNS TABLE ({_ROW_TABLE_SPEC})
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT {_ROW_COLUMNS} FROM public.ocr_benchmark_batch_runs
            ORDER BY started_at DESC
            LIMIT 1
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.get_latest_batch_run() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.get_latest_batch_run() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.get_latest_batch_run() TO {_APP_ROLE}")

    op.execute(
        f"""
        CREATE FUNCTION public.get_batch_run(p_id uuid)
        RETURNS TABLE ({_ROW_TABLE_SPEC})
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT {_ROW_COLUMNS} FROM public.ocr_benchmark_batch_runs WHERE id = p_id
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.get_batch_run(uuid) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.get_batch_run(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.get_batch_run(uuid) TO {_APP_ROLE}")

    op.execute(
        f"""
        CREATE FUNCTION public.insert_running_batch_run(p_total integer)
        RETURNS TABLE ({_ROW_TABLE_SPEC})
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            INSERT INTO public.ocr_benchmark_batch_runs (status, total)
            VALUES ('running', p_total)
            RETURNING {_ROW_COLUMNS}
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.insert_running_batch_run(integer) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.insert_running_batch_run(integer) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.insert_running_batch_run(integer) TO {_APP_ROLE}"
    )

    op.execute(
        """
        CREATE FUNCTION public.advance_batch_run_progress(p_id uuid, p_failed boolean)
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
    op.execute(
        f"ALTER FUNCTION public.advance_batch_run_progress(uuid, boolean) OWNER TO {_DEFINER_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION public.advance_batch_run_progress(uuid, boolean) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.advance_batch_run_progress(uuid, boolean) "
        f"TO {_APP_ROLE}"
    )

    op.execute(
        """
        CREATE FUNCTION public.finish_batch_run(p_id uuid, p_status text)
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
                -- Solo si sigue `running` (mismo criterio que el `_mark_failed` original): si el
                -- bucle por candidato ya lo dejó `done`, no lo pisa hacia atrás.
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
    op.execute("DROP FUNCTION IF EXISTS public.finish_batch_run(uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS public.advance_batch_run_progress(uuid, boolean)")
    op.execute("DROP FUNCTION IF EXISTS public.insert_running_batch_run(integer)")
    op.execute("DROP FUNCTION IF EXISTS public.get_batch_run(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.get_latest_batch_run()")
    op.execute("DROP FUNCTION IF EXISTS public.get_running_batch_run()")

    op.execute(f"REVOKE ALL ON public.ocr_benchmark_batch_runs FROM {_DEFINER_ROLE}")
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON public.ocr_benchmark_batch_runs TO {_APP_ROLE}"
    )

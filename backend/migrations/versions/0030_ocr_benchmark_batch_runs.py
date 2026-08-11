"""Panel de lote retroactivo del benchmark real (S6.7 Área C, spec
docs/specs/S6.7-benchmark-real-motor-variante.md §0.5, C10-C17): tabla `ocr_benchmark_batch_runs`
(progreso persistido en Postgres, sobrevive a un reinicio de la API/worker) + función `SECURITY
DEFINER` `ocr_benchmark_candidates(p_limit)` (descubrimiento de candidatos A TRAVÉS de todos los
tenants, mismo patrón que `ocr_ranking_candidates`/0019 y `ocr_backfill_candidates`/0018).

`ocr_benchmark_batch_runs` es una tabla de OPERACIÓN DE PLATAFORMA, sin `tenant_id` y SIN RLS (a
diferencia de TODAS las tablas de negocio del proyecto hasta ahora): no guarda ningún dato de
tenant, solo el progreso agregado de un lote lanzado por un `admin-tech` desde el panel de
plataforma. La única protección de acceso es el propio endpoint HTTP (`require_admin_tech()`), no
la RLS -- se lee/escribe directamente con `identity.session` (`shared.db.platform_session`, sin
contexto de tenant), sin necesitar ninguna función `SECURITY DEFINER` para ESTA tabla en concreto
(spec, ver `platform_admin/benchmark_batch_repository.py`).

Un candidato es una factura CONFIRMADA (la propia existencia de la fila en `invoices` ya lo implica:
solo `invoicing.service.confirm` inserta ahí, spec §2 "verdad confirmada"), `is_test = false` (spec
§5.2, "fuera del lote retroactivo"), cuyo `uploaded_file_id` tiene MENOS de 18 filas en
`ocr_benchmark_results` (3 variantes x 6 motores, spec §0.5) -- ordenadas por `confirmed_at` DESC,
`LIMIT p_limit`. El `GRANT SELECT` de `autoken_definer` sobre `invoices` ya lo concedió 0012
(`platform_tenant_metrics`, tabla completa, no por columnas): no se repite aquí. Solo hace falta uno
nuevo sobre `ocr_benchmark_results` (0029 no se lo concedió: esa migración todavía no tenía ninguna
función `SECURITY DEFINER` que lo necesitara).

Registra el modelo ORM en `platform_admin/models.py` (el guard `alembic check` de CI compara el
esquema completo, no solo tablas con RLS -- verificado explícitamente para esta migración tras el
hallazgo crítico real de la parte 2 de esta misma tarea, donde justo esto faltaba).

Revision ID: 0030_ocr_benchmark_batch_runs
Revises: 0029_ocr_benchmark_results
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0030_ocr_benchmark_batch_runs"
down_revision = "0029_ocr_benchmark_results"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"

# 3 variantes (original/enhanced/clahe) x 6 motores = 18 combinaciones por factura (spec §0.5/§2).
_COMBINATIONS_PER_FILE = 18


def upgrade() -> None:
    op.create_table(
        "ocr_benchmark_batch_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False),
        sa.Column("completed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="ocr_benchmark_batch_runs_status_check",
        ),
    )
    # Sin RLS a propósito (ver docstring del módulo): cualquier fila es visible/editable por el rol
    # runtime, la única protección de acceso es el propio endpoint HTTP.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ocr_benchmark_batch_runs TO {_APP_ROLE}")

    op.execute(
        f"GRANT SELECT (uploaded_file_id) ON public.ocr_benchmark_results TO {_DEFINER_ROLE}"
    )

    op.execute(
        f"""
        CREATE FUNCTION public.ocr_benchmark_candidates(p_limit integer)
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
              AND COALESCE(b.combinations, 0) < {_COMBINATIONS_PER_FILE}
            ORDER BY i.confirmed_at DESC
            LIMIT p_limit
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.ocr_benchmark_candidates(integer) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.ocr_benchmark_candidates(integer) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.ocr_benchmark_candidates(integer) TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.ocr_benchmark_candidates(integer)")
    op.execute(
        f"REVOKE SELECT (uploaded_file_id) ON public.ocr_benchmark_results FROM {_DEFINER_ROLE}"
    )
    op.execute(f"REVOKE ALL ON ocr_benchmark_batch_runs FROM {_APP_ROLE}")
    op.drop_table("ocr_benchmark_batch_runs")

"""Ranking multi-modelo (S4.8): tabla `ocr_ranking_entries` + descubrimiento de candidatos.

Generaliza el patrón de `ocr_comparison_runs` (S2.10, 0018) de 2 lecturas fijas ("original"/
"realzada") a N motores: una fila por `(uploaded_file_id, engine)`, no una fila por fichero con
columnas fijas — así el número de motores del ranking puede crecer sin migrar el esquema. RLS de
dos niveles idéntica al resto de tablas de OCR; `UniqueConstraint(uploaded_file_id, engine)` da la
idempotencia del reprocesado (upsert por motor, no duplica).

`ocr_ranking_candidates()` (SECURITY DEFINER, mismo patrón que `ocr_backfill_candidates`/0018 y
`platform_tenant_metrics`/0012): un fichero es candidato si NO tiene NINGUNA entrada de ranking
todavía (no se trackea qué motores concretos le faltan — ver spec S4.8 §5, para no complicar el
descubrimiento con una noción de "parcialmente rankeado"). Solo proyecta IDs + `content_type`
(el filtro de formato soportado vive en Python, `ocr.preprocess.enhance.SUPPORTED_CONTENT_TYPES`,
mismo criterio que 0018). Reutiliza el `GRANT SELECT` sobre `uploaded_files` que 0018 YA concedió a
`autoken_definer` (exactamente las mismas columnas: `tenant_id`/`company_id`/`id`/`content_type`/
`status`) — no se repite aquí a propósito: si esta migración concediera y luego revocara ese mismo
grant en su `downgrade`, un downgrade de 0019 sin downgradear 0018 le quitaría a
`ocr_backfill_candidates` (0018) un privilegio que sigue necesitando. Solo se concede/revoca lo
NUEVO de esta migración: `SELECT` sobre la propia `ocr_ranking_entries`.

Revision ID: 0019_ocr_ranking_entries
Revises: 0018_ocr_comparison_runs
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_ocr_ranking_entries"
down_revision = "0018_ocr_comparison_runs"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.create_table(
        "ocr_ranking_entries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("reading", postgresql.JSONB(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "uploaded_file_id", "engine", name="ocr_ranking_entries_file_engine_unique"
        ),
    )

    op.execute("ALTER TABLE ocr_ranking_entries ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ocr_ranking_entries FORCE ROW LEVEL SECURITY")
    tenant_setting = "NULLIF(current_setting('app.tenant_id', true), '')"
    company_setting = "NULLIF(current_setting('app.company_id', true), '')"
    isolation = (
        f"tenant_id = {tenant_setting}::uuid "
        f"AND ({company_setting} IS NULL OR company_id = {company_setting}::uuid)"
    )
    op.execute(
        f"CREATE POLICY ocr_ranking_entries_tenant_isolation ON ocr_ranking_entries "
        f"USING ({isolation}) WITH CHECK ({isolation})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ocr_ranking_entries TO {_APP_ROLE}")

    # El GRANT sobre `uploaded_files` para `autoken_definer` ya lo concedió 0018 (mismas columnas
    # exactas que necesita esta función) — no se repite aquí (ver docstring del módulo). Sobre
    # `ocr_ranking_entries` sí hace falta uno nuevo: `uploaded_file_id` para el anti-join de
    # candidatos, `engine`/`score` para el agregado del panel (`ocr_ranking_summary`, más abajo).
    op.execute(
        f"GRANT SELECT (uploaded_file_id, engine, score) "
        f"ON public.ocr_ranking_entries TO {_DEFINER_ROLE}"
    )

    op.execute(
        """
        CREATE FUNCTION public.ocr_ranking_candidates()
        RETURNS TABLE (tenant_id uuid, company_id uuid, uploaded_file_id uuid, content_type text)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT uf.tenant_id, uf.company_id, uf.id, uf.content_type
            FROM public.uploaded_files uf
            LEFT JOIN public.ocr_ranking_entries r ON r.uploaded_file_id = uf.id
            WHERE uf.status IN ('ocr_done', 'needs_review')
              AND r.uploaded_file_id IS NULL
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.ocr_ranking_candidates() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.ocr_ranking_candidates() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.ocr_ranking_candidates() TO {_APP_ROLE}")

    # Agregado por motor para el panel admin-tech (C11): un `platform_admin` no tiene tenant (S1.3),
    # así que su sesión nunca fija `app.tenant_id`/`app.company_id` — un SELECT normal sobre
    # `ocr_ranking_entries` (RLS FORCE) le devolvería 0 filas de TODOS los tenants. Igual que
    # `platform_tenant_metrics` (0012), la agregación cruzando tenants vive en una función
    # `SECURITY DEFINER`, no en una consulta Python bajo RLS. Empate a puntuación máxima cuenta para
    # todos los empatados (C11 — ningún desempate arbitrario).
    op.execute(
        """
        CREATE FUNCTION public.ocr_ranking_summary()
        RETURNS TABLE (
            engine text,
            invoices_read bigint,
            average_score double precision,
            first_place_count bigint
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            WITH best_per_file AS (
                SELECT uploaded_file_id, MAX(score) AS best_score
                FROM public.ocr_ranking_entries
                GROUP BY uploaded_file_id
            )
            SELECT
                r.engine,
                COUNT(*) AS invoices_read,
                AVG(r.score)::float AS average_score,
                COUNT(*) FILTER (WHERE r.score = b.best_score) AS first_place_count
            FROM public.ocr_ranking_entries r
            JOIN best_per_file b ON b.uploaded_file_id = r.uploaded_file_id
            GROUP BY r.engine
            ORDER BY average_score DESC, r.engine
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.ocr_ranking_summary() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.ocr_ranking_summary() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.ocr_ranking_summary() TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.ocr_ranking_summary()")
    op.execute("DROP FUNCTION IF EXISTS public.ocr_ranking_candidates()")
    op.execute(
        f"REVOKE SELECT (uploaded_file_id, engine, score) "
        f"ON public.ocr_ranking_entries FROM {_DEFINER_ROLE}"
    )
    op.execute("DROP POLICY IF EXISTS ocr_ranking_entries_tenant_isolation ON ocr_ranking_entries")
    op.drop_table("ocr_ranking_entries")

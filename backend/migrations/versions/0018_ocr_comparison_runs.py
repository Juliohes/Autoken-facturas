"""Comparativa original-vs-realzada (S2.9/S2.10): tabla `ocr_comparison_runs` + descubrimiento de
candidatos para el backfill retroactivo.

Crea `ocr_comparison_runs` con el mismo patrón de RLS de dos niveles que `ocr_extractions` (0005):
`FORCE ROW LEVEL SECURITY` por `app.tenant_id` + `app.company_id`, UNIQUE `(uploaded_file_id)` para
una comparativa vigente por fichero (idempotencia del reprocesado, igual que la extracción), y grants
mínimos (SELECT/INSERT/UPDATE, sin DELETE) al rol runtime.

Además crea `ocr_backfill_candidates()`, función `SECURITY DEFINER` que lista, A TRAVÉS de todos los
tenants, los ficheros ya procesados con éxito (`ocr_done`/`needs_review`) que todavía no tienen
comparativa — mismo patrón ya auditado que `list_tenants`/`platform_tenant_metrics` (S4.1/S4.5) para
leer a través de la frontera de tenant sin que el rol runtime necesite un permiso general de lectura
cruzada. Es de solo lectura (no escribe nada, no invoca al lector de IA): el backfill real que sí
escribe pasa por el camino normal de `ocr_comparison_runs` (RLS del tenant correspondiente), fichero
a fichero. El filtro de "formato de imagen soportado" NO vive aquí (auditoría: evita duplicar
`ocr.preprocess.enhance.SUPPORTED_CONTENT_TYPES` en SQL y Python sin guardarraíl que los mantenga
sincronizados) — la función devuelve también `content_type` y quien la llama (`ocr.backfill_repository`)
filtra en Python contra esa única fuente de verdad. Los `GRANT SELECT` a `autoken_definer` son a
nivel de COLUMNA (mínimo privilegio): la función nunca necesita ver `storage_bucket`/`storage_key`/
`sha256`/`uploaded_by` de `uploaded_files`.

Revision ID: 0018_ocr_comparison_runs
Revises: 0017_admin_tech_settings
Create Date: 2026-07-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_ocr_comparison_runs"
down_revision = "0017_admin_tech_settings"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.create_table(
        "ocr_comparison_runs",
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
        sa.Column("original_reading", postgresql.JSONB(), nullable=False),
        sa.Column("enhanced_reading", postgresql.JSONB(), nullable=False),
        sa.Column("original_score", sa.Integer(), nullable=False),
        sa.Column("enhanced_score", sa.Integer(), nullable=False),
        sa.Column("winner", sa.Text(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("uploaded_file_id", name="ocr_comparison_runs_uploaded_file_unique"),
        sa.CheckConstraint(
            "winner IN ('original', 'enhanced', 'tie')", name="ocr_comparison_runs_winner_valid"
        ),
    )

    op.execute("ALTER TABLE ocr_comparison_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ocr_comparison_runs FORCE ROW LEVEL SECURITY")
    tenant_setting = "NULLIF(current_setting('app.tenant_id', true), '')"
    company_setting = "NULLIF(current_setting('app.company_id', true), '')"
    isolation = (
        f"tenant_id = {tenant_setting}::uuid "
        f"AND ({company_setting} IS NULL OR company_id = {company_setting}::uuid)"
    )
    op.execute(
        f"CREATE POLICY ocr_comparison_runs_tenant_isolation ON ocr_comparison_runs "
        f"USING ({isolation}) WITH CHECK ({isolation})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ocr_comparison_runs TO {_APP_ROLE}")

    # `autoken_definer` tiene BYPASSRLS (0002) pero eso no da SELECT sobre una tabla por sí solo: cada
    # tabla que lea una función SECURITY DEFINER suya necesita su propio GRANT explícito (mismo
    # patrón ya establecido en 0012 para `platform_tenant_metrics`). `uploaded_files` es de 0004, sin
    # este grant hasta ahora porque ninguna función `autoken_definer` la había necesitado leer. A
    # nivel de columna (mínimo privilegio, precedente 0005 `GRANT UPDATE (status)`): la función solo
    # necesita estas 5 (incluida `status`, que usa en el WHERE, no solo en el SELECT — un GRANT de
    # columna cubre TODA referencia a la columna en la consulta, no solo la lista de proyección),
    # nunca `storage_bucket`/`storage_key`/`sha256`/`uploaded_by`.
    op.execute(
        f"GRANT SELECT (tenant_id, company_id, id, content_type, status) "
        f"ON public.uploaded_files TO {_DEFINER_ROLE}"
    )
    op.execute(f"GRANT SELECT (uploaded_file_id) ON public.ocr_comparison_runs TO {_DEFINER_ROLE}")

    op.execute(
        """
        CREATE FUNCTION public.ocr_backfill_candidates()
        RETURNS TABLE (tenant_id uuid, company_id uuid, uploaded_file_id uuid, content_type text)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT uf.tenant_id, uf.company_id, uf.id, uf.content_type
            FROM public.uploaded_files uf
            LEFT JOIN public.ocr_comparison_runs cr ON cr.uploaded_file_id = uf.id
            WHERE uf.status IN ('ocr_done', 'needs_review')
              AND cr.uploaded_file_id IS NULL
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.ocr_backfill_candidates() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.ocr_backfill_candidates() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.ocr_backfill_candidates() TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.ocr_backfill_candidates()")
    op.execute(f"REVOKE SELECT (uploaded_file_id) ON public.ocr_comparison_runs FROM {_DEFINER_ROLE}")
    op.execute(
        f"REVOKE SELECT (tenant_id, company_id, id, content_type, status) "
        f"ON public.uploaded_files FROM {_DEFINER_ROLE}"
    )
    op.execute("DROP POLICY IF EXISTS ocr_comparison_runs_tenant_isolation ON ocr_comparison_runs")
    op.drop_table("ocr_comparison_runs")

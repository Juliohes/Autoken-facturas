"""Ejemplos concretos por motor del ranking multi-modelo (2026-08-09, a petición de Julio: "quiero
más contexto [en el panel de Ranking OCR], ver ejemplos concretos, no solo números").

`ocr_ranking_summary()` (migración 0019) agrega por motor A TRAVÉS de todos los tenants, pero solo
proyecta `(uploaded_file_id, engine, score)` a `autoken_definer` — no basta para mostrar QUÉ leyó
un motor de verdad. `ocr_ranking_examples(engine, limit)` (mismo patrón `SECURITY DEFINER`, misma
`autoken_definer`) añade el `GRANT` sobre `reading`/`model`/`created_at` (las columnas que faltaban)
y devuelve las lecturas más recientes de un motor concreto, sin acotar a un tenant.

Revision ID: 0028_ocr_ranking_examples
Revises: 0027_invoice_number
Create Date: 2026-08-09
"""

from __future__ import annotations

from alembic import op

revision = "0028_ocr_ranking_examples"
down_revision = "0027_invoice_number"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(
        f"GRANT SELECT (reading, model, created_at) "
        f"ON public.ocr_ranking_entries TO {_DEFINER_ROLE}"
    )

    op.execute(
        """
        CREATE FUNCTION public.ocr_ranking_examples(p_engine text, p_limit integer DEFAULT 5)
        RETURNS TABLE (uploaded_file_id uuid, model text, reading jsonb, score integer)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT uploaded_file_id, model, reading, score
            FROM public.ocr_ranking_entries
            WHERE engine = p_engine
            ORDER BY created_at DESC
            LIMIT p_limit
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION public.ocr_ranking_examples(text, integer) OWNER TO {_DEFINER_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION public.ocr_ranking_examples(text, integer) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.ocr_ranking_examples(text, integer) TO {_APP_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.ocr_ranking_examples(text, integer)")
    op.execute(
        f"REVOKE SELECT (reading, model, created_at) "
        f"ON public.ocr_ranking_entries FROM {_DEFINER_ROLE}"
    )

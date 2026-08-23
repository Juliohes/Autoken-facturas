"""Separa los controles OCR de laboratorio de la política de producción (R-046)."""

from __future__ import annotations

from alembic import op


revision = "0050_r046_ocr_lab_settings"
down_revision = "0049_r038_supplier_profiles"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.platform_settings
            ADD COLUMN ocr_lab_visible boolean NOT NULL DEFAULT false,
            ADD COLUMN ocr_auto_benchmark_enabled boolean NOT NULL DEFAULT false,
            ADD COLUMN ocr_benchmark_engines jsonb NOT NULL DEFAULT '["tesseract"]'::jsonb,
            ADD COLUMN ocr_benchmark_variants jsonb NOT NULL
                DEFAULT '["original", "enhanced", "clahe"]'::jsonb;
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.get_ocr_lab_settings()
        RETURNS TABLE (
            lab_visible boolean,
            auto_benchmark_enabled boolean,
            benchmark_engines jsonb,
            benchmark_variants jsonb
        )
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT ocr_lab_visible, ocr_auto_benchmark_enabled,
                   ocr_benchmark_engines, ocr_benchmark_variants
            FROM public.platform_settings
            WHERE id = true
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.get_ocr_lab_settings() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.get_ocr_lab_settings() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.get_ocr_lab_settings() TO {_APP_ROLE}")
    op.execute(
        """
        CREATE FUNCTION public.set_ocr_lab_settings(
            p_lab_visible boolean,
            p_auto_benchmark_enabled boolean,
            p_benchmark_engines jsonb,
            p_benchmark_variants jsonb
        )
        RETURNS TABLE (
            lab_visible boolean,
            auto_benchmark_enabled boolean,
            benchmark_engines jsonb,
            benchmark_variants jsonb
        )
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            UPDATE public.platform_settings
            SET ocr_lab_visible = p_lab_visible,
                ocr_auto_benchmark_enabled = p_auto_benchmark_enabled,
                ocr_benchmark_engines = p_benchmark_engines,
                ocr_benchmark_variants = p_benchmark_variants
            WHERE id = true;
            RETURN QUERY SELECT * FROM public.get_ocr_lab_settings();
        END;
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION public.set_ocr_lab_settings(boolean, boolean, jsonb, jsonb) "
        f"OWNER TO {_DEFINER_ROLE}"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.set_ocr_lab_settings(boolean, boolean, jsonb, jsonb) FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.set_ocr_lab_settings(boolean, boolean, jsonb, jsonb) "
        f"TO {_APP_ROLE}"
    )
    op.execute(
        """
        CREATE TABLE public.ocr_policy_promotions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id uuid NOT NULL REFERENCES public.users(id),
            old_policy jsonb NOT NULL,
            new_policy jsonb NOT NULL,
            promoted_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("GRANT SELECT, INSERT ON public.ocr_policy_promotions TO autoken_app")
    op.execute("REVOKE UPDATE, DELETE ON public.ocr_policy_promotions FROM autoken_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.ocr_policy_promotions")
    op.execute("DROP FUNCTION IF EXISTS public.set_ocr_lab_settings(boolean, boolean, jsonb, jsonb)")
    op.execute("DROP FUNCTION IF EXISTS public.get_ocr_lab_settings()")
    op.execute(
        """
        ALTER TABLE public.platform_settings
            DROP COLUMN ocr_benchmark_variants,
            DROP COLUMN ocr_benchmark_engines,
            DROP COLUMN ocr_auto_benchmark_enabled,
            DROP COLUMN ocr_lab_visible
        """
    )

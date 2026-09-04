"""Política OCR de producción versionada y administrable (R-033)."""

from __future__ import annotations

from alembic import op

revision = "0048_r033_ocr_policy"
down_revision = "0047_r032_candidate_count"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE public.platform_settings
            ADD COLUMN ocr_policy_version integer NOT NULL DEFAULT 1,
            ADD COLUMN ocr_primary_engine text NOT NULL DEFAULT 'gemini-3.5-flash',
            ADD COLUMN ocr_primary_model text NOT NULL DEFAULT 'gemini-3.5-flash',
            ADD COLUMN ocr_fallback_enabled boolean NOT NULL DEFAULT false,
            ADD COLUMN ocr_fallback_engine text DEFAULT 'mistral-ocr-4',
            ADD COLUMN ocr_fallback_model text DEFAULT 'mistral-ocr-4-0',
            ADD COLUMN ocr_consensus_mode text NOT NULL DEFAULT 'primary_only';
        """
    )
    op.execute(
        """
        ALTER TABLE public.platform_settings
            ADD CONSTRAINT platform_settings_ocr_policy_version_check
                CHECK (ocr_policy_version >= 1),
            ADD CONSTRAINT platform_settings_ocr_policy_consensus_check
                CHECK (ocr_consensus_mode IN ('primary_only', 'per_field')),
            ADD CONSTRAINT platform_settings_ocr_fallback_complete_check
                CHECK (
                    (ocr_fallback_engine IS NULL AND ocr_fallback_model IS NULL)
                    OR (ocr_fallback_engine IS NOT NULL AND ocr_fallback_model IS NOT NULL)
                );
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.get_ocr_policy()
        RETURNS TABLE (
            version integer,
            primary_engine text,
            primary_model text,
            fallback_enabled boolean,
            fallback_engine text,
            fallback_model text,
            consensus_mode text
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT ocr_policy_version, ocr_primary_engine, ocr_primary_model,
                   ocr_fallback_enabled, ocr_fallback_engine, ocr_fallback_model,
                   ocr_consensus_mode
            FROM public.platform_settings
            WHERE id = true
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.get_ocr_policy() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.get_ocr_policy() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.get_ocr_policy() TO {_APP_ROLE}")

    op.execute(
        """
        CREATE FUNCTION public.set_ocr_policy(
            p_version integer,
            p_primary_engine text,
            p_primary_model text,
            p_fallback_enabled boolean,
            p_fallback_engine text,
            p_fallback_model text,
            p_consensus_mode text
        )
        RETURNS TABLE (
            version integer,
            primary_engine text,
            primary_model text,
            fallback_enabled boolean,
            fallback_engine text,
            fallback_model text,
            consensus_mode text
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            UPDATE public.platform_settings
            SET ocr_policy_version = p_version,
                ocr_primary_engine = p_primary_engine,
                ocr_primary_model = p_primary_model,
                ocr_fallback_enabled = p_fallback_enabled,
                ocr_fallback_engine = p_fallback_engine,
                ocr_fallback_model = p_fallback_model,
                ocr_consensus_mode = p_consensus_mode
            WHERE id = true;
            RETURN QUERY SELECT * FROM public.get_ocr_policy();
        END;
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION public.set_ocr_policy(integer, text, text, boolean, text, text, text) "
        f"OWNER TO {_DEFINER_ROLE}"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.set_ocr_policy("
        "integer, text, text, boolean, text, text, text) FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.set_ocr_policy("
        f"integer, text, text, boolean, text, text, text) TO {_APP_ROLE}"
    )


def downgrade() -> None:
    op.execute(
        "DROP FUNCTION IF EXISTS public.set_ocr_policy("
        "integer, text, text, boolean, text, text, text)"
    )
    op.execute("DROP FUNCTION IF EXISTS public.get_ocr_policy()")
    op.execute(
        "ALTER TABLE public.platform_settings "
        "DROP CONSTRAINT platform_settings_ocr_fallback_complete_check, "
        "DROP CONSTRAINT platform_settings_ocr_policy_consensus_check, "
        "DROP CONSTRAINT platform_settings_ocr_policy_version_check"
    )
    op.execute(
        "ALTER TABLE public.platform_settings "
        "DROP COLUMN ocr_consensus_mode, DROP COLUMN ocr_fallback_model, "
        "DROP COLUMN ocr_fallback_engine, DROP COLUMN ocr_fallback_enabled, "
        "DROP COLUMN ocr_primary_model, DROP COLUMN ocr_primary_engine, "
        "DROP COLUMN ocr_policy_version"
    )

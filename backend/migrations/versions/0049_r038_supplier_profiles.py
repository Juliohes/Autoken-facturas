"""Perfiles de proveedor scoped por tenant y empresa (R-038)."""

from __future__ import annotations

from alembic import op

revision = "0049_r038_supplier_profiles"
down_revision = "0048_r033_ocr_policy"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE public.supplier_profiles (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
            company_id uuid NOT NULL REFERENCES public.companies(id) ON DELETE CASCADE,
            counterparty_cif_blind_index text NOT NULL,
            confirmations integer NOT NULL DEFAULT 0 CHECK (confirmations >= 0),
            invoice_number_patterns jsonb NOT NULL DEFAULT '[]'::jsonb,
            tax_rate_histogram jsonb NOT NULL DEFAULT '{}'::jsonb,
            tax_line_count_histogram jsonb NOT NULL DEFAULT '{}'::jsonb,
            field_correction_stats jsonb NOT NULL DEFAULT '{}'::jsonb,
            last_seen_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT supplier_profiles_scope_unique
                UNIQUE (tenant_id, company_id, counterparty_cif_blind_index)
        )
        """
    )
    op.execute("ALTER TABLE public.supplier_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.supplier_profiles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY supplier_profiles_scope ON public.supplier_profiles
        USING (
            tenant_id = current_setting('app.tenant_id', true)::uuid
            AND company_id = current_setting('app.company_id', true)::uuid
        )
        WITH CHECK (
            tenant_id = current_setting('app.tenant_id', true)::uuid
            AND company_id = current_setting('app.company_id', true)::uuid
        )
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.supplier_profiles TO autoken_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS public.supplier_profiles")

"""Permite a la asesoría supervisar perfiles de proveedor de sus empresas (R-051)."""

from __future__ import annotations

from alembic import op


revision = "0053_r051_supplier_profile_rls"
down_revision = "0052_r048_ocr_eta_samples"
branch_labels = None
depends_on = None


def _policy_sql(policy_name: str) -> str:
    tenant_setting = "NULLIF(current_setting('app.tenant_id', true), '')"
    company_setting = "NULLIF(current_setting('app.company_id', true), '')"
    isolation = (
        f"tenant_id = {tenant_setting}::uuid "
        f"AND ({company_setting} IS NULL OR company_id = {company_setting}::uuid)"
    )
    return (
        f"CREATE POLICY {policy_name} ON public.supplier_profiles "
        f"USING ({isolation}) WITH CHECK ({isolation})"
    )


def upgrade() -> None:
    op.execute("DROP POLICY supplier_profiles_scope ON public.supplier_profiles")
    op.execute(_policy_sql("supplier_profiles_scope"))


def downgrade() -> None:
    op.execute("DROP POLICY supplier_profiles_scope ON public.supplier_profiles")
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

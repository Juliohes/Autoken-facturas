"""Amplía `platform_tenant_metrics()` (S4.5) a petición de Julio (2026-08-01): separa
`active_users_count` en `admins_count`/`users_count` (antes mezclaba `tenant_admin` y `user` en una
sola cifra) y añade `invoices_total_count` (todas las facturas confirmadas no-test del tenant,
distinto de `invoices_this_month` y de `ocr_extractions_count` — hay facturas importadas que nunca
pasan por OCR, spec: "facturas totales... no son igual que facturas procesadas").

Postgres no permite `ALTER FUNCTION` para cambiar `RETURNS TABLE`: se hace `DROP` + `CREATE` de la
misma función, mismo patrón que el resto de funciones `SECURITY DEFINER` del proyecto. Ningún grant
de tabla nuevo: `autoken_definer` ya tenía `SELECT` sobre `users`/`invoices` desde 0003/0012.

Revision ID: 0025_tenant_metrics_v2
Revises: 0024_password_reset
Create Date: 2026-08-01
"""

from __future__ import annotations

from alembic import op

revision = "0025_tenant_metrics_v2"
down_revision = "0024_password_reset"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"

_OLD_FUNCTION_SQL = """
    CREATE FUNCTION public.platform_tenant_metrics()
    RETURNS TABLE (
        tenant_id uuid,
        slug text,
        name text,
        companies_count bigint,
        active_users_count bigint,
        invoices_this_month bigint,
        ocr_extractions_count bigint,
        last_activity_at timestamptz
    )
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, pg_temp
    AS $$
        SELECT
            t.id,
            t.slug::text,
            t.name,
            COALESCE(cc.companies_count, 0),
            COALESCE(uc.active_users_count, 0),
            COALESCE(ic.invoices_this_month, 0),
            COALESCE(oc.ocr_extractions_count, 0),
            ac.last_activity_at
        FROM public.tenants t
        LEFT JOIN (
            SELECT c.tenant_id, COUNT(*) AS companies_count
            FROM public.companies c
            GROUP BY c.tenant_id
        ) cc ON cc.tenant_id = t.id
        LEFT JOIN (
            SELECT u.tenant_id, COUNT(*) AS active_users_count
            FROM public.users u
            WHERE u.status = 'active'
            GROUP BY u.tenant_id
        ) uc ON uc.tenant_id = t.id
        LEFT JOIN (
            SELECT i.tenant_id, COUNT(*) AS invoices_this_month
            FROM public.invoices i
            WHERE i.is_test = false
              AND i.confirmed_at >= date_trunc('month', now())
            GROUP BY i.tenant_id
        ) ic ON ic.tenant_id = t.id
        LEFT JOIN (
            SELECT o.tenant_id, COUNT(*) AS ocr_extractions_count
            FROM public.ocr_extractions o
            GROUP BY o.tenant_id
        ) oc ON oc.tenant_id = t.id
        LEFT JOIN (
            SELECT a.tenant_id, MAX(a.at) AS last_activity_at
            FROM public.audit_log a
            GROUP BY a.tenant_id
        ) ac ON ac.tenant_id = t.id
        ORDER BY t.slug
    $$;
"""

_NEW_FUNCTION_SQL = """
    CREATE FUNCTION public.platform_tenant_metrics()
    RETURNS TABLE (
        tenant_id uuid,
        slug text,
        name text,
        companies_count bigint,
        admins_count bigint,
        users_count bigint,
        invoices_this_month bigint,
        invoices_total_count bigint,
        ocr_extractions_count bigint,
        last_activity_at timestamptz
    )
    LANGUAGE sql
    STABLE
    SECURITY DEFINER
    SET search_path = pg_catalog, pg_temp
    AS $$
        SELECT
            t.id,
            t.slug::text,
            t.name,
            COALESCE(cc.companies_count, 0),
            COALESCE(uc.admins_count, 0),
            COALESCE(uc.users_count, 0),
            COALESCE(ic.invoices_this_month, 0),
            COALESCE(itc.invoices_total_count, 0),
            COALESCE(oc.ocr_extractions_count, 0),
            ac.last_activity_at
        FROM public.tenants t
        LEFT JOIN (
            SELECT c.tenant_id, COUNT(*) AS companies_count
            FROM public.companies c
            GROUP BY c.tenant_id
        ) cc ON cc.tenant_id = t.id
        LEFT JOIN (
            SELECT
                u.tenant_id,
                COUNT(*) FILTER (WHERE u.role = 'tenant_admin') AS admins_count,
                COUNT(*) FILTER (WHERE u.role = 'user') AS users_count
            FROM public.users u
            WHERE u.status = 'active'
            GROUP BY u.tenant_id
        ) uc ON uc.tenant_id = t.id
        LEFT JOIN (
            SELECT i.tenant_id, COUNT(*) AS invoices_this_month
            FROM public.invoices i
            WHERE i.is_test = false
              AND i.confirmed_at >= date_trunc('month', now())
            GROUP BY i.tenant_id
        ) ic ON ic.tenant_id = t.id
        LEFT JOIN (
            SELECT i.tenant_id, COUNT(*) AS invoices_total_count
            FROM public.invoices i
            WHERE i.is_test = false
              AND i.confirmed_at IS NOT NULL
            GROUP BY i.tenant_id
        ) itc ON itc.tenant_id = t.id
        LEFT JOIN (
            SELECT o.tenant_id, COUNT(*) AS ocr_extractions_count
            FROM public.ocr_extractions o
            GROUP BY o.tenant_id
        ) oc ON oc.tenant_id = t.id
        LEFT JOIN (
            SELECT a.tenant_id, MAX(a.at) AS last_activity_at
            FROM public.audit_log a
            GROUP BY a.tenant_id
        ) ac ON ac.tenant_id = t.id
        ORDER BY t.slug
    $$;
"""


def _replace_function(sql: str) -> None:
    op.execute("DROP FUNCTION IF EXISTS public.platform_tenant_metrics()")
    op.execute(sql)
    op.execute(f"ALTER FUNCTION public.platform_tenant_metrics() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.platform_tenant_metrics() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.platform_tenant_metrics() TO {_APP_ROLE}")


def upgrade() -> None:
    _replace_function(_NEW_FUNCTION_SQL)


def downgrade() -> None:
    _replace_function(_OLD_FUNCTION_SQL)

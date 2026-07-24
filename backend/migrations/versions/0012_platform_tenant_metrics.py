"""Métricas y consumo por tenant en el panel de plataforma (S4.5, ADR-0001 patrón `SECURITY
DEFINER`).

`GET /platform/tenants/metrics` necesita cruzar TODOS los tenants a la vez (empresas, usuarios
activos, facturas de este mes, extracciones OCR, última actividad), el mismo problema que ya
resolvió `list_tenants()` (S4.1, migración 0010): sin `app.tenant_id` fijado, el rol runtime
(`autoken_app`) no ve más de un tenant en la misma consulta bajo la RLS de dos niveles de
`companies`/`users`/`invoices`/`ocr_extractions`/`audit_log`. Se añade una función nueva,
`platform_tenant_metrics()`, mismo patrón que `list_tenants`/`create_tenant`: propiedad de
`autoken_definer` (`BYPASSRLS`), `REVOKE ALL FROM PUBLIC` + `GRANT EXECUTE` solo a `autoken_app`.

`autoken_definer` ya tenía `SELECT` sobre `tenants` (0002) y `users` (0003), pero nunca sobre
`companies`/`invoices`/`ocr_extractions`/`audit_log` — esta migración concede exactamente ese
`SELECT` (de solo lectura, ningún `INSERT`/`UPDATE`/`DELETE` nuevo).

Cada contador se agrega en una subconsulta propia, una fila por tenant, ANTES de unirla a
`tenants` (`LEFT JOIN` 1-a-1 por `tenant_id`): unir directamente varias relaciones 1-a-N entre sí
en el mismo `SELECT` multiplicaría filas antes de agregar (mismo error que la auditoría de S3.4
encontró y corrigió en `reporting.repository.list_companies`; no se repite aquí).

Revision ID: 0012_platform_tenant_metrics
Revises: 0011_tenant_demo_lifecycle
Create Date: 2026-07-24
"""

from __future__ import annotations

from alembic import op

revision = "0012_platform_tenant_metrics"
down_revision = "0011_tenant_demo_lifecycle"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(f"GRANT SELECT ON public.companies TO {_DEFINER_ROLE}")
    op.execute(f"GRANT SELECT ON public.invoices TO {_DEFINER_ROLE}")
    op.execute(f"GRANT SELECT ON public.ocr_extractions TO {_DEFINER_ROLE}")
    op.execute(f"GRANT SELECT ON public.audit_log TO {_DEFINER_ROLE}")

    op.execute(
        """
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
    )
    op.execute(f"ALTER FUNCTION public.platform_tenant_metrics() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.platform_tenant_metrics() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.platform_tenant_metrics() TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.platform_tenant_metrics()")
    op.execute(f"REVOKE SELECT ON public.audit_log FROM {_DEFINER_ROLE}")
    op.execute(f"REVOKE SELECT ON public.ocr_extractions FROM {_DEFINER_ROLE}")
    op.execute(f"REVOKE SELECT ON public.invoices FROM {_DEFINER_ROLE}")
    op.execute(f"REVOKE SELECT ON public.companies FROM {_DEFINER_ROLE}")

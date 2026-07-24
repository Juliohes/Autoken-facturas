"""Dominio propio de cliente: asignarlo/quitarlo y resolver tenant por él (S4.6, alcance acotado —
ver docs/specs/S4.6-dominios-propios.md §0; Caddy/TLS real e infra quedan fuera de esta migración).

`tenants.custom_domain` ya existe desde 0001 (`Text`, `UNIQUE`, nullable), sin ningún camino para
leerlo/escribirlo. Esta migración, mismo patrón `SECURITY DEFINER` que el resto del módulo:

- `resolve_tenant_by_custom_domain(p_host)`: mismo contrato público que `resolve_tenant(slug)`
  (0002) — mismos campos, solo tenants `status = 'active'`. El middleware la usa como fallback
  cuando la resolución por subdominio no encuentra nada (spec §3 decisión 2).
- `set_tenant_custom_domain(p_tenant_id, p_custom_domain)`: asigna o quita (`NULL`) el dominio
  propio de un tenant. Alias `t` en el `UPDATE`/`RETURN QUERY` (igual que `convert_tenant_to_production`,
  0011) para evitar la ambigüedad de PL/pgSQL entre columna y variable OUT del propio
  `RETURNS TABLE`. Si el id no existe, 0 filas -> el `repository` lo traduce a 404, sin excepción SQL.
- `list_tenants()` se reemplaza (`DROP`+`CREATE`, Postgres no permite ampliar el conjunto de
  columnas de un `RETURNS TABLE` vía `CREATE OR REPLACE`) para incluir `custom_domain` en su
  respuesta (spec §3 decisión 3).

Ningún grant nuevo de tabla: `autoken_definer` ya tenía `SELECT`+`UPDATE` sobre `tenants` (0002/0011).

Revision ID: 0013_tenant_custom_domain
Revises: 0012_platform_tenant_metrics
Create Date: 2026-07-24
"""

from __future__ import annotations

from alembic import op

revision = "0013_tenant_custom_domain"
down_revision = "0012_platform_tenant_metrics"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION public.resolve_tenant_by_custom_domain(p_host text)
        RETURNS TABLE (id uuid, slug text, name text, is_demo boolean)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT id, slug, name, is_demo
            FROM public.tenants
            WHERE custom_domain = p_host AND status = 'active'
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION public.resolve_tenant_by_custom_domain(text) OWNER TO {_DEFINER_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION public.resolve_tenant_by_custom_domain(text) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.resolve_tenant_by_custom_domain(text) TO {_APP_ROLE}"
    )

    op.execute(
        """
        CREATE FUNCTION public.set_tenant_custom_domain(p_tenant_id uuid, p_custom_domain text)
        RETURNS TABLE (
            id uuid, slug text, name text, status text, is_demo boolean, created_at timestamptz,
            custom_domain text
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            UPDATE public.tenants AS t SET custom_domain = p_custom_domain
                WHERE t.id = p_tenant_id;
            RETURN QUERY
                SELECT t.id, t.slug::text, t.name, t.status, t.is_demo, t.created_at,
                       t.custom_domain
                FROM public.tenants t WHERE t.id = p_tenant_id;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.set_tenant_custom_domain(uuid, text) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.set_tenant_custom_domain(uuid, text) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.set_tenant_custom_domain(uuid, text) TO {_APP_ROLE}"
    )

    op.execute(f"REVOKE ALL ON FUNCTION public.list_tenants() FROM {_APP_ROLE}")
    op.execute("DROP FUNCTION public.list_tenants()")
    op.execute(
        """
        CREATE FUNCTION public.list_tenants()
        RETURNS TABLE (
            id uuid, slug text, name text, status text, is_demo boolean, created_at timestamptz,
            custom_domain text
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT id, slug::text, name, status, is_demo, created_at, custom_domain
            FROM public.tenants
            ORDER BY created_at DESC
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.list_tenants() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.list_tenants() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.list_tenants() TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON FUNCTION public.list_tenants() FROM {_APP_ROLE}")
    op.execute("DROP FUNCTION public.list_tenants()")
    op.execute(
        """
        CREATE FUNCTION public.list_tenants()
        RETURNS TABLE (
            id uuid, slug text, name text, status text, is_demo boolean, created_at timestamptz
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT id, slug::text, name, status, is_demo, created_at
            FROM public.tenants
            ORDER BY created_at DESC
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.list_tenants() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.list_tenants() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.list_tenants() TO {_APP_ROLE}")

    op.execute("DROP FUNCTION IF EXISTS public.set_tenant_custom_domain(uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS public.resolve_tenant_by_custom_domain(text)")

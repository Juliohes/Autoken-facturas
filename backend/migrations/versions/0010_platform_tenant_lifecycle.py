"""Alta y listado de tenants desde el panel de plataforma (S4.1, ADR-0001 patrón `SECURITY DEFINER`).

`tenants` se aísla por su propio `id` (S1.1, la única tabla así): con esa RLS, ninguna sesión puede
ver TODAS las filas a la vez (falta para listar) ni insertar una fila sin que su `id` ya casara con
`app.tenant_id` de antemano (falta para el alta). El rol runtime además solo tiene `SELECT` sobre
`tenants` a propósito desde 0001 ("el alta/baja/suspensión de asesorías es de plataforma, no de la
API"). Esta migración NO toca esa RLS ni ese grant: añade dos funciones `SECURITY DEFINER` nuevas,
mismo patrón que `resolve_tenant` (0002) y `find_platform_admin` (0003) — propiedad del rol ya
existente `autoken_definer` (`BYPASSRLS`), único camino acotado para saltar la RLS de `tenants`:

- `create_tenant(...)`: inserta `tenants` + `tenant_branding` en una única función, atómica (o las
  dos filas, o ninguna; sin bloque `EXCEPTION`, así que cualquier fallo aborta toda la transacción
  de `platform_session`). El id lo sigue generando la columna (`server_default gen_random_uuid()`,
  0001), única fuente; la función solo lo recoge con `RETURNING ... INTO` para enlazar el branding.
- `list_tenants()`: todas las filas de `tenants`, más reciente primero (spec S4.1 §3 C7). Sin
  filtros: el volumen esperado (asesorías dadas de alta una a una) no los necesita.

Ningún cambio a la RLS de `tenants`/`tenant_branding` ni a los grants de tabla del rol runtime sobre
ellas: solo `EXECUTE` sobre estas dos funciones.

Revision ID: 0010_platform_tenant_lifecycle
Revises: 0009_purge_test_invoices
Create Date: 2026-07-23
"""

from __future__ import annotations

from alembic import op

revision = "0010_platform_tenant_lifecycle"
down_revision = "0009_purge_test_invoices"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    # El definer ya tiene SELECT sobre `tenants` (0002); le falta INSERT ahí y en `tenant_branding`
    # (tabla nueva para él) para poder ejecutar `create_tenant`.
    op.execute(f"GRANT INSERT ON public.tenants TO {_DEFINER_ROLE}")
    op.execute(f"GRANT INSERT ON public.tenant_branding TO {_DEFINER_ROLE}")

    op.execute(
        """
        CREATE FUNCTION public.create_tenant(
            p_slug text,
            p_name text,
            p_logo_url text,
            p_color_primary text,
            p_color_secondary text,
            p_app_name text
        )
        RETURNS TABLE (
            id uuid, slug text, name text, status text, is_demo boolean, created_at timestamptz
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
            v_id uuid;
        BEGIN
            INSERT INTO public.tenants AS t (slug, name)
                VALUES (p_slug, p_name) RETURNING t.id INTO v_id;
            INSERT INTO public.tenant_branding
                (tenant_id, logo_url, color_primary, color_secondary, app_name)
                VALUES (v_id, p_logo_url, p_color_primary, p_color_secondary,
                        COALESCE(p_app_name, p_name));
            RETURN QUERY
                SELECT t.id, t.slug::text, t.name, t.status, t.is_demo, t.created_at
                FROM public.tenants t WHERE t.id = v_id;
        END;
        $$;
        """
    )
    op.execute("ALTER FUNCTION public.create_tenant(text, text, text, text, text, text) "
               f"OWNER TO {_DEFINER_ROLE}")
    op.execute(
        "REVOKE ALL ON FUNCTION public.create_tenant(text, text, text, text, text, text) "
        "FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION public.create_tenant(text, text, text, text, text, text) "
        f"TO {_APP_ROLE}"
    )

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


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.list_tenants()")
    op.execute(
        "DROP FUNCTION IF EXISTS public.create_tenant(text, text, text, text, text, text)"
    )
    op.execute(f"REVOKE INSERT ON public.tenant_branding FROM {_DEFINER_ROLE}")
    op.execute(f"REVOKE INSERT ON public.tenants FROM {_DEFINER_ROLE}")

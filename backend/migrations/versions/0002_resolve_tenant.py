"""Función `resolve_tenant(slug)` para el lookup subdominio->tenant pre-contexto (S1.2, issue #48).

La RLS de `tenants` (S1.1) aísla por su propio `id`, así que el rol runtime no puede leer un tenant
por `slug` sin tener ya su id. Esta función `SECURITY DEFINER` es el ÚNICO camino acotado para
resolver un subdominio a tenant antes de tener contexto: devuelve solo campos PÚBLICOS del tenant
**activo** y no abre ninguna otra lectura de `tenants`.

Una función `SECURITY DEFINER` corre con los privilegios de su **propietaria**, y como `tenants`
tiene `FORCE ROW LEVEL SECURITY`, un propietario normal (no superusuario, sin BYPASSRLS) TAMBIÉN
quedaría sujeto a la RLS y la función devolvería 0 filas para todo tenant. Para que funcione igual
en test/CI y en producción (independiente de quién corra las migraciones), la función la posee un
rol dedicado **`autoken_definer` con BYPASSRLS** (NOLOGIN, no superusuario). Crear un rol BYPASSRLS
exige que la migración la corra un superusuario (el bootstrap habitual).

`SET search_path = pg_catalog, pg_temp` (con `public.tenants` cualificado) blinda contra secuestro
por search_path, patrón obligatorio en SECURITY DEFINER. Se revoca a PUBLIC y se concede EXECUTE
solo al rol runtime.

Revision ID: 0002_resolve_tenant
Revises: 0001_tenancy_core_rls
Create Date: 2026-07-07
"""

from __future__ import annotations

from alembic import op

revision = "0002_resolve_tenant"
down_revision = "0001_tenancy_core_rls"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    # Rol dueño de la función: BYPASSRLS para que la SECURITY DEFINER salte la RLS de tenants
    # también en producción (no depende de que la migración la corra un superusuario más allá de
    # la propia creación del rol). NOLOGIN: nadie se conecta con él.
    op.execute(
        f"""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{_DEFINER_ROLE}') THEN
            CREATE ROLE {_DEFINER_ROLE} NOLOGIN NOSUPERUSER NOINHERIT
              NOCREATEDB NOCREATEROLE BYPASSRLS;
          END IF;
        END $$;
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.resolve_tenant(p_slug text)
        RETURNS TABLE (id uuid, slug text, name text, is_demo boolean)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT id, slug, name, is_demo
            FROM public.tenants
            WHERE slug = p_slug AND status = 'active'
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.resolve_tenant(text) OWNER TO {_DEFINER_ROLE}")
    # BYPASSRLS salta la seguridad de FILA, pero el privilegio de TABLA es aparte: el definer
    # necesita SELECT sobre tenants para leerla dentro de la función.
    op.execute(f"GRANT SELECT ON public.tenants TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.resolve_tenant(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.resolve_tenant(text) TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.resolve_tenant(text)")
    # El rol es a nivel de clúster; se deja (puede compartirse con otras BDs del mismo servidor).

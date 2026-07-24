"""Modo demo: alta con `is_demo`, convertir a producción y purgar (S4.4, ADR-0001 patrón
`SECURITY DEFINER`).

`tenants.is_demo` ya existe desde 0001 (`boolean not null default false`), pero `create_tenant`
(0010) nunca lo escribía: todo alta creaba `is_demo=false` siempre. Esta migración:

- **Reemplaza `create_tenant`** (se elimina la firma de 6 argumentos y se crea la de 7, con
  `p_is_demo boolean` al final) para que el alta pueda marcar el tenant como demo. `CREATE OR
  REPLACE` no vale aquí: cambiar el número de parámetros de entrada crea una función distinta
  (sobrecarga), no sustituye la existente; se elimina explícitamente para no dejar las dos.
- **`convert_tenant_to_production(p_tenant_id)`**: pone `is_demo=false`. Idempotente (si ya era
  `false`, el `UPDATE` no afecta filas pero la función igualmente devuelve el tenant actual); si el
  id no existe, devuelve cero filas (el `repository` lo traduce a 404, sin lanzar ninguna excepción
  SQL para ese caso).
- **`purge_demo_tenant(p_tenant_id)`**: `DELETE ... WHERE id = ... AND is_demo = true RETURNING id`.
  La condición "solo demo" vive fija en el propio SQL (spec S4.4 decisión 3), nunca en un parámetro
  que el cliente pudiera falsear. Cascada ya confirmada (S1.1 y siguientes: todas las tablas con
  datos de tenant tienen `ondelete="CASCADE"` hasta `tenants.id`, excepto `cif_lookups`, caché
  global sin `tenant_id`, ADR-0011). El `DELETE` en `tenants` no necesita ningún grant nuevo sobre
  las tablas hijas: el motor de Postgres aplica la cascada de claves foráneas sin comprobar
  privilegios de DML del rol invocador sobre esas tablas (el chequeo de privilegios es solo sobre
  la tabla referenciada, `tenants`, que es la que gana el nuevo `GRANT DELETE`); el rol
  `autoken_definer` ya tiene `BYPASSRLS` (0002), así que la cascada tampoco tropieza con la RLS de
  las tablas hijas.

Revision ID: 0011_tenant_demo_lifecycle
Revises: 0010_platform_tenant_lifecycle
Create Date: 2026-07-24
"""

from __future__ import annotations

from alembic import op

revision = "0011_tenant_demo_lifecycle"
down_revision = "0010_platform_tenant_lifecycle"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"

_OLD_CREATE_TENANT_SIG = "text, text, text, text, text, text"
_NEW_CREATE_TENANT_SIG = "text, text, text, text, text, text, boolean"


def upgrade() -> None:
    op.execute(
        f"REVOKE ALL ON FUNCTION public.create_tenant({_OLD_CREATE_TENANT_SIG}) FROM {_APP_ROLE}"
    )
    op.execute(f"DROP FUNCTION public.create_tenant({_OLD_CREATE_TENANT_SIG})")

    op.execute(
        """
        CREATE FUNCTION public.create_tenant(
            p_slug text,
            p_name text,
            p_logo_url text,
            p_color_primary text,
            p_color_secondary text,
            p_app_name text,
            p_is_demo boolean
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
            INSERT INTO public.tenants AS t (slug, name, is_demo)
                VALUES (p_slug, p_name, COALESCE(p_is_demo, false)) RETURNING t.id INTO v_id;
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
    op.execute(
        f"ALTER FUNCTION public.create_tenant({_NEW_CREATE_TENANT_SIG}) OWNER TO {_DEFINER_ROLE}"
    )
    op.execute(f"REVOKE ALL ON FUNCTION public.create_tenant({_NEW_CREATE_TENANT_SIG}) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.create_tenant({_NEW_CREATE_TENANT_SIG}) TO {_APP_ROLE}"
    )

    # `tenants` solo tenía SELECT (0002)/INSERT (0010) para el definer; el modo demo necesita
    # también UPDATE (convertir a producción) y DELETE (purgar). Ningún grant nuevo sobre tablas
    # hijas: la cascada de FKs no los necesita (ver docstring del módulo).
    op.execute(f"GRANT UPDATE, DELETE ON public.tenants TO {_DEFINER_ROLE}")

    op.execute(
        """
        CREATE FUNCTION public.convert_tenant_to_production(p_tenant_id uuid)
        RETURNS TABLE (
            id uuid, slug text, name text, status text, is_demo boolean, created_at timestamptz
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            UPDATE public.tenants AS t SET is_demo = false
                WHERE t.id = p_tenant_id AND t.is_demo = true;
            RETURN QUERY
                SELECT t.id, t.slug::text, t.name, t.status, t.is_demo, t.created_at
                FROM public.tenants t WHERE t.id = p_tenant_id;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.convert_tenant_to_production(uuid) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.convert_tenant_to_production(uuid) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.convert_tenant_to_production(uuid) TO {_APP_ROLE}"
    )

    # `existed`/`was_demo`/`purged` en vez de un simple `DELETE ... RETURNING id`: el `SELECT ...
    # FOR UPDATE` bloquea la fila del tenant hasta el commit, así que dos purgas/conversiones
    # concurrentes sobre el mismo id se serializan (nunca hay una carrera entre "comprobar si es
    # demo" y "borrar" — ambas cosas ocurren dentro de la misma función, sin round-trip a Python de
    # por medio). Devolver el resultado explícito evita que `platform_admin.service` tenga que
    # adivinar (con un pre-chequeo aparte y un `assert`) por qué no se borró ninguna fila.
    op.execute(
        """
        CREATE FUNCTION public.purge_demo_tenant(p_tenant_id uuid)
        RETURNS TABLE (existed boolean, was_demo boolean, purged boolean)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
            v_is_demo boolean;
        BEGIN
            SELECT t.is_demo INTO v_is_demo FROM public.tenants t WHERE t.id = p_tenant_id
                FOR UPDATE;
            IF NOT FOUND THEN
                RETURN QUERY SELECT false, false, false;
                RETURN;
            END IF;
            IF NOT v_is_demo THEN
                RETURN QUERY SELECT true, false, false;
                RETURN;
            END IF;
            DELETE FROM public.tenants WHERE id = p_tenant_id;
            RETURN QUERY SELECT true, true, true;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.purge_demo_tenant(uuid) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.purge_demo_tenant(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.purge_demo_tenant(uuid) TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.purge_demo_tenant(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.convert_tenant_to_production(uuid)")
    op.execute(f"REVOKE UPDATE, DELETE ON public.tenants FROM {_DEFINER_ROLE}")

    op.execute(
        f"REVOKE ALL ON FUNCTION public.create_tenant({_NEW_CREATE_TENANT_SIG}) FROM {_APP_ROLE}"
    )
    op.execute(f"DROP FUNCTION IF EXISTS public.create_tenant({_NEW_CREATE_TENANT_SIG})")

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
    op.execute(
        f"ALTER FUNCTION public.create_tenant({_OLD_CREATE_TENANT_SIG}) OWNER TO {_DEFINER_ROLE}"
    )
    op.execute(f"REVOKE ALL ON FUNCTION public.create_tenant({_OLD_CREATE_TENANT_SIG}) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.create_tenant({_OLD_CREATE_TENANT_SIG}) TO {_APP_ROLE}"
    )

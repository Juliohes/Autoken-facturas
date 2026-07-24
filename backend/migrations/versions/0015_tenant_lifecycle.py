"""Ciclo de vida completo de un tenant: suspender/reactivar/exportar/borrar (S4.7, ADR-0001 patrón
`SECURITY DEFINER`).

Añade `tenants.last_export_at` (nullable) y cuatro funciones nuevas, mismo patrón que S4.4/S4.6:

- `suspend_tenant(p_tenant_id)`/`reactivate_tenant(p_tenant_id)`: ponen `status`. Idempotentes
  (mismo criterio que `convert_tenant_to_production`, S4.4); 0 filas si el id no existe. El efecto
  (bloquear el login) ya existía desde S1.2/S1.6 — esto solo añade el camino para escribir el campo.
- `mark_tenant_exported(p_tenant_id)`: pone `last_export_at = now()` tras generar un export con
  éxito (S4.7 §3 decisión 2).
- `delete_tenant(p_tenant_id, p_confirm_slug)`: `SELECT ... FOR UPDATE` + `DELETE`, misma técnica
  atómica que `purge_demo_tenant` (S4.4, migración 0011) para no repetir la carrera que esa tarea
  encontró y corrigió. Devuelve `(existed, slug_matched, exported, deleted)` explícito: el
  `repository` no tiene que adivinar por qué no se borró nada. La condición completa —existe, el
  slug de confirmación coincide, y hay al menos un export previo (`last_export_at IS NOT NULL`,
  sin exigir que sea "reciente", spec §0 decisión 4)— vive fija en el propio SQL.

Ningún grant de tabla nuevo: `autoken_definer` ya tenía `SELECT`/`UPDATE`/`DELETE` sobre `tenants`
(0002/0011).

Revision ID: 0015_tenant_lifecycle
Revises: 0014_convert_prod_custom_domain
Create Date: 2026-07-24
"""

from __future__ import annotations

from alembic import op

revision = "0015_tenant_lifecycle"
down_revision = "0014_convert_prod_custom_domain"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"

_TENANT_OUT_COLUMNS = (
    "id uuid, slug text, name text, status text, is_demo boolean, created_at timestamptz, "
    "custom_domain text"
)
_TENANT_OUT_SELECT = (
    "t.id, t.slug::text, t.name, t.status, t.is_demo, t.created_at, t.custom_domain"
)


def upgrade() -> None:
    op.execute("ALTER TABLE public.tenants ADD COLUMN last_export_at timestamptz")

    op.execute(
        f"""
        CREATE FUNCTION public.suspend_tenant(p_tenant_id uuid)
        RETURNS TABLE ({_TENANT_OUT_COLUMNS})
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            UPDATE public.tenants AS t SET status = 'suspended' WHERE t.id = p_tenant_id;
            RETURN QUERY
                SELECT {_TENANT_OUT_SELECT} FROM public.tenants t WHERE t.id = p_tenant_id;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.suspend_tenant(uuid) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.suspend_tenant(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.suspend_tenant(uuid) TO {_APP_ROLE}")

    op.execute(
        f"""
        CREATE FUNCTION public.reactivate_tenant(p_tenant_id uuid)
        RETURNS TABLE ({_TENANT_OUT_COLUMNS})
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            UPDATE public.tenants AS t SET status = 'active' WHERE t.id = p_tenant_id;
            RETURN QUERY
                SELECT {_TENANT_OUT_SELECT} FROM public.tenants t WHERE t.id = p_tenant_id;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.reactivate_tenant(uuid) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.reactivate_tenant(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.reactivate_tenant(uuid) TO {_APP_ROLE}")

    op.execute(
        """
        CREATE FUNCTION public.mark_tenant_exported(p_tenant_id uuid)
        RETURNS TABLE (id uuid, last_export_at timestamptz)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            UPDATE public.tenants AS t SET last_export_at = now() WHERE t.id = p_tenant_id;
            RETURN QUERY
                SELECT t.id, t.last_export_at FROM public.tenants t WHERE t.id = p_tenant_id;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.mark_tenant_exported(uuid) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.mark_tenant_exported(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.mark_tenant_exported(uuid) TO {_APP_ROLE}")

    op.execute(
        """
        CREATE FUNCTION public.delete_tenant(p_tenant_id uuid, p_confirm_slug text)
        RETURNS TABLE (existed boolean, slug_matched boolean, exported boolean, deleted boolean)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        DECLARE
            v_slug text;
            v_last_export_at timestamptz;
        BEGIN
            SELECT t.slug, t.last_export_at INTO v_slug, v_last_export_at
                FROM public.tenants t WHERE t.id = p_tenant_id FOR UPDATE;
            IF NOT FOUND THEN
                RETURN QUERY SELECT false, false, false, false;
                RETURN;
            END IF;
            IF v_slug IS DISTINCT FROM p_confirm_slug THEN
                RETURN QUERY SELECT true, false, (v_last_export_at IS NOT NULL), false;
                RETURN;
            END IF;
            IF v_last_export_at IS NULL THEN
                RETURN QUERY SELECT true, true, false, false;
                RETURN;
            END IF;
            DELETE FROM public.tenants WHERE id = p_tenant_id;
            RETURN QUERY SELECT true, true, true, true;
        END;
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION public.delete_tenant(uuid, text) OWNER TO {_DEFINER_ROLE}"
    )
    op.execute("REVOKE ALL ON FUNCTION public.delete_tenant(uuid, text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.delete_tenant(uuid, text) TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.delete_tenant(uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS public.mark_tenant_exported(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.reactivate_tenant(uuid)")
    op.execute("DROP FUNCTION IF EXISTS public.suspend_tenant(uuid)")
    op.execute("ALTER TABLE public.tenants DROP COLUMN last_export_at")

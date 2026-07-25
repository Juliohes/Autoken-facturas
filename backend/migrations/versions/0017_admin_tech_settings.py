"""Interruptor admin-tech (S4.10, prerrequisito de S2.9/S2.10/S4.8): un flag `is_admin_tech` sobre
una cuenta `platform_admin` ya existente (decisión de Julio, no un rol nuevo en el enum cerrado) +
una tabla de ajuste global de un único interruptor.

- `users.is_admin_tech boolean NOT NULL DEFAULT false`: nunca se activa desde la aplicación (spec
  §0 decisión 2), solo a mano en Postgres, igual que hoy se da de alta el primer `platform_admin`.
- `platform_settings`: tabla de una sola fila (patrón `id boolean PRIMARY KEY DEFAULT true CHECK
  (id)`, garantiza que nunca pueda existir una segunda fila) con `ocr_experiment_enabled` — el
  interruptor único que gobernará S2.9/S2.10/S4.8 (tareas futuras; esta migración no engancha nada
  al pipeline OCR todavía).
- `find_platform_admin_by_id` (migración 0016) se sustituye (DROP+CREATE, no se puede cambiar el
  conjunto de columnas de salida con `CREATE OR REPLACE`, precedente ya establecido en S4.4/S4.6/
  S4.7) para devolver también `is_admin_tech`, que `/auth/me` necesita exponer (S4.10 decisión 5).
- `get_platform_settings()`/`set_platform_settings(p_enabled)`: mismo patrón `SECURITY DEFINER` que
  el resto de operaciones de plataforma, aunque `platform_settings` no tiene RLS de tenant que
  saltar — se mantiene por consistencia con el resto del contexto `platform_admin` (la barrera real
  de "solo admin-tech" vive en el guard HTTP, `require_admin_tech`, no en la función SQL en sí).

Revision ID: 0017_admin_tech_settings
Revises: 0016_platform_admin_me
Create Date: 2026-07-24
"""

from __future__ import annotations

from alembic import op

revision = "0017_admin_tech_settings"
down_revision = "0016_platform_admin_me"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute("ALTER TABLE public.users ADD COLUMN is_admin_tech boolean NOT NULL DEFAULT false")

    op.execute("DROP FUNCTION IF EXISTS public.find_platform_admin_by_id(uuid)")
    op.execute(
        """
        CREATE FUNCTION public.find_platform_admin_by_id(p_id uuid)
        RETURNS TABLE (id uuid, email text, role text, is_admin_tech boolean)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT id, email, role, is_admin_tech
            FROM public.users
            WHERE id = p_id AND role = 'platform_admin' AND tenant_id IS NULL
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.find_platform_admin_by_id(uuid) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.find_platform_admin_by_id(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.find_platform_admin_by_id(uuid) TO {_APP_ROLE}")

    op.execute(
        """
        CREATE TABLE public.platform_settings (
            id boolean PRIMARY KEY DEFAULT true CHECK (id),
            ocr_experiment_enabled boolean NOT NULL DEFAULT false
        )
        """
    )
    op.execute("INSERT INTO public.platform_settings (id, ocr_experiment_enabled) VALUES (true, false)")
    op.execute(f"GRANT SELECT, UPDATE ON public.platform_settings TO {_DEFINER_ROLE}")

    op.execute(
        """
        CREATE FUNCTION public.get_platform_settings()
        RETURNS TABLE (ocr_experiment_enabled boolean)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT ocr_experiment_enabled FROM public.platform_settings WHERE id = true
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.get_platform_settings() OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.get_platform_settings() FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.get_platform_settings() TO {_APP_ROLE}")

    op.execute(
        """
        CREATE FUNCTION public.set_platform_settings(p_ocr_experiment_enabled boolean)
        RETURNS TABLE (ocr_experiment_enabled boolean)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            UPDATE public.platform_settings
                SET ocr_experiment_enabled = p_ocr_experiment_enabled
                WHERE id = true;
            RETURN QUERY
                SELECT ps.ocr_experiment_enabled FROM public.platform_settings ps WHERE ps.id = true;
        END;
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.set_platform_settings(boolean) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.set_platform_settings(boolean) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.set_platform_settings(boolean) TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.set_platform_settings(boolean)")
    op.execute("DROP FUNCTION IF EXISTS public.get_platform_settings()")
    op.execute("DROP TABLE IF EXISTS public.platform_settings")

    op.execute("DROP FUNCTION IF EXISTS public.find_platform_admin_by_id(uuid)")
    op.execute(
        """
        CREATE FUNCTION public.find_platform_admin_by_id(p_id uuid)
        RETURNS TABLE (id uuid, email text, role text)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT id, email, role
            FROM public.users
            WHERE id = p_id AND role = 'platform_admin' AND tenant_id IS NULL
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.find_platform_admin_by_id(uuid) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.find_platform_admin_by_id(uuid) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.find_platform_admin_by_id(uuid) TO {_APP_ROLE}")

    op.execute("ALTER TABLE public.users DROP COLUMN is_admin_tech")

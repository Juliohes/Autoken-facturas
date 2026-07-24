"""Hotfix: `find_platform_admin_by_id(id)`, para que `GET /auth/me` pueda leer la identidad de un
`platform_admin` por su `user_id` (JWT `sub`), no solo por email.

`find_platform_admin(email)` (migración 0003) solo sirve al login (busca por email antes de tener un
token). `/auth/me` ya tiene el `user_id` del token verificado y necesita el camino equivalente por id
— sin él, la RLS bloquea el `SELECT` directo (mismo criterio que protege el resto de `users`) y un
`platform_admin` no puede leer su propia identidad tras iniciar sesión (regresión real desde que S4.9
empezó a llamar `/auth/me` también para el login de plataforma).

Mismo patrón `SECURITY DEFINER` que `find_platform_admin` (0003): propiedad de `autoken_definer`,
`REVOKE ALL FROM PUBLIC` + `GRANT EXECUTE` solo a `autoken_app`.

Revision ID: 0016_platform_admin_me
Revises: 0015_tenant_lifecycle
Create Date: 2026-07-24
"""

from __future__ import annotations

from alembic import op

revision = "0016_platform_admin_me"
down_revision = "0015_tenant_lifecycle"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
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


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.find_platform_admin_by_id(uuid)")

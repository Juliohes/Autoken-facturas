"""Alta/baja de cuentas sembradas (sin autoservicio): platform_admin y tenant_admin/user.

Hasta ahora, crear un `platform_admin` o un `tenant_admin`/`user` que no pasa por el registro
autoservicio de S1.4 exigía un INSERT SQL suelto contra la BD real con el rol superusuario — el
propio docstring de `identity/activation.py` ya avisaba de este hueco ("en producción emite un
script de plataforma" que nunca llegó a versionarse). Esta migración cierra ese hueco con tres
funciones `SECURITY DEFINER` (mismo patrón que `create_tenant`, 0004, y `find_platform_admin`,
0003): dueño `autoken_definer` (BYPASSRLS, NOLOGIN, no superusuario), `SET search_path` blindado,
`REVOKE ALL FROM PUBLIC` + `GRANT EXECUTE` acotado al rol runtime. Consumidas por
`identity.repository`/`scripts/create_account.py`, nunca por una conexión de superusuario embebida
en código de aplicación.

- `provision_platform_admin(email, is_admin_tech)`: alta de un `platform_admin` (`tenant_id NULL`,
  `password_hash NULL` — se fija en la activación, S1.3).
- `provision_tenant_account(tenant_id, email, role)`: alta de un `tenant_admin`/`user` sembrado
  directamente (sin el registro+aprobación de S1.4); `role='platform_admin'` se rechaza en la propia
  función (ese camino es el otro, no este).
- `revoke_platform_admin(email)`: baja de un `platform_admin` existente (DELETE); usado para
  degradar una cuenta de plataforma a una cuenta de tenant normal — son dos pasos atómicos
  independientes (baja aquí + alta con `provision_tenant_account`), nunca un UPDATE que reasigne
  `role`+`tenant_id` a la vez sobre la misma fila (evita arrastrar `password_hash`/`totp_secret` ya
  fijados de la cuenta de plataforma a la cuenta nueva).

El definer ya tenía `SELECT, UPDATE` sobre `users` desde 0003; aquí se amplía a `INSERT, DELETE`
(estrictamente lo que estas tres funciones necesitan, nada más).

Revision ID: 0023_account_provisioning
Revises: 0022_legacy_bcrypt_migration
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op

revision = "0023_account_provisioning"
down_revision = "0022_legacy_bcrypt_migration"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(f"GRANT INSERT, DELETE ON public.users TO {_DEFINER_ROLE}")

    op.execute(
        """
        CREATE FUNCTION public.provision_platform_admin(p_email text, p_is_admin_tech boolean)
        RETURNS TABLE (id uuid, email text, role text, is_admin_tech boolean)
        LANGUAGE sql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            INSERT INTO public.users (id, tenant_id, email, role, status, is_admin_tech)
            VALUES (gen_random_uuid(), NULL, p_email, 'platform_admin', 'active', p_is_admin_tech)
            RETURNING id, email, role, is_admin_tech
        $$;
        """
    )

    op.execute(
        """
        CREATE FUNCTION public.provision_tenant_account(p_tenant_id uuid, p_email text, p_role text)
        RETURNS TABLE (id uuid, email text, role text)
        LANGUAGE plpgsql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            IF p_role NOT IN ('tenant_admin', 'user') THEN
                RAISE EXCEPTION 'invalid_role: % (solo tenant_admin o user)', p_role;
            END IF;
            RETURN QUERY
                INSERT INTO public.users (id, tenant_id, email, role, status)
                VALUES (gen_random_uuid(), p_tenant_id, p_email, p_role, 'active')
                RETURNING users.id, users.email, users.role;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE FUNCTION public.revoke_platform_admin(p_email text)
        RETURNS TABLE (id uuid)
        LANGUAGE sql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            DELETE FROM public.users
            WHERE email = p_email AND role = 'platform_admin' AND tenant_id IS NULL
            RETURNING id
        $$;
        """
    )

    for signature in (
        "public.provision_platform_admin(text, boolean)",
        "public.provision_tenant_account(uuid, text, text)",
        "public.revoke_platform_admin(text)",
    ):
        op.execute(f"ALTER FUNCTION {signature} OWNER TO {_DEFINER_ROLE}")
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.revoke_platform_admin(text)")
    op.execute("DROP FUNCTION IF EXISTS public.provision_tenant_account(uuid, text, text)")
    op.execute("DROP FUNCTION IF EXISTS public.provision_platform_admin(text, boolean)")
    op.execute(f"REVOKE INSERT, DELETE ON public.users FROM {_DEFINER_ROLE}")

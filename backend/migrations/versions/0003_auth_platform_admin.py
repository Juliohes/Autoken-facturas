"""Auth S1.3: `platform_admin` sin tenant + funciones acotadas de login/activación (SECURITY DEFINER).

Enmienda a ADR-0001 (ver ADR-0012): un `platform_admin` no pertenece a ninguna asesoría, así que
`users.tenant_id` pasa a ser NULLABLE, atado por un CHECK a que el rol y la pertenencia sean
coherentes: `(role = 'platform_admin') = (tenant_id IS NULL)`. Como `UNIQUE(tenant_id, email)` no
impide dos platform_admin con el mismo email (los NULL son distintos), se añade un índice único
parcial de email donde `tenant_id IS NULL`.

Los usuarios sin tenant son invisibles al rol runtime por la RLS de S1.1 (ningún contexto de tenant
casa su fila). Para operar sobre ellos por un camino ACOTADO se añaden tres funciones
`SECURITY DEFINER` con el mismo patrón que `resolve_tenant` (0002): dueño `autoken_definer`
(BYPASSRLS, NOLOGIN, no superusuario), `SET search_path` blindado, `REVOKE ALL FROM PUBLIC` +
`GRANT EXECUTE` al rol runtime:
- `find_platform_admin(email)`: ÚNICO camino para autenticar a un `platform_admin` en `panel`.
- `activation_set_password(user_id, hash)`: fija la contraseña en la activación (solo si aún no la
  tiene) y devuelve email/rol; gobernada por el token de activación de un solo uso.
- `activation_enroll_totp(user_id, secret)`: enrola el secreto TOTP al confirmar la activación.

La RLS de S1.1 queda intacta; el rol runtime sigue NOBYPASSRLS.

Revision ID: 0003_auth_platform_admin
Revises: 0002_resolve_tenant
Create Date: 2026-07-08
"""

from __future__ import annotations

from alembic import op

revision = "0003_auth_platform_admin"
down_revision = "0002_resolve_tenant"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    # 1) `platform_admin` sin asesoría: tenant_id nullable, atado por CHECK al rol.
    op.execute("ALTER TABLE users ALTER COLUMN tenant_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT users_platform_admin_no_tenant "
        "CHECK ((role = 'platform_admin') = (tenant_id IS NULL))"
    )
    # Email único entre platform_admin (los NULL de UNIQUE(tenant_id, email) no lo garantizan).
    op.execute(
        "CREATE UNIQUE INDEX ux_users_platform_email ON users (email) WHERE tenant_id IS NULL"
    )

    # 2) El definer necesita SELECT/UPDATE de tabla sobre users (BYPASSRLS salta la RLS de FILA, no
    #    el privilegio de TABLA). El rol `autoken_definer` ya existe (0002).
    op.execute(f"GRANT SELECT, UPDATE ON public.users TO {_DEFINER_ROLE}")

    # 3) find_platform_admin(email): localiza al platform_admin (sin tenant) por email, saltando la
    #    RLS de forma acotada. Único camino de autenticación en `panel`.
    op.execute(
        """
        CREATE FUNCTION public.find_platform_admin(p_email text)
        RETURNS TABLE (
            id uuid, email text, role text, status text, password_hash text, totp_secret text
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT id, email, role, status, password_hash, totp_secret
            FROM public.users
            WHERE email = p_email AND role = 'platform_admin' AND tenant_id IS NULL
        $$;
        """
    )

    # 4) activation_set_password: fija la contraseña SOLO si la cuenta es ACTIVABLE y devuelve
    #    email/rol. Contrato "cuenta activable = status='active' + password_hash IS NULL" (ver
    #    ADR-0012): el guard atómico del WHERE evita reactivar una cuenta ya activada (F4) y también
    #    activar una cuenta pendiente de aprobación (la transición pending->active es gate de S1.4).
    op.execute(
        """
        CREATE FUNCTION public.activation_set_password(p_user_id uuid, p_hash text)
        RETURNS TABLE (id uuid, email text, role text)
        LANGUAGE sql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            UPDATE public.users
            SET password_hash = p_hash
            WHERE id = p_user_id AND status = 'active' AND password_hash IS NULL
            RETURNING id, email, role
        $$;
        """
    )

    # 5) activation_enroll_totp: enrola el secreto TOTP en la cuenta al confirmar la activación.
    #    Guard simétrico con activation_set_password (F3): solo si aún no hay secreto, para no
    #    permitir re-enrolar un segundo factor sobre una cuenta que ya lo tiene.
    op.execute(
        """
        CREATE FUNCTION public.activation_enroll_totp(p_user_id uuid, p_secret text)
        RETURNS void
        LANGUAGE sql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            UPDATE public.users SET totp_secret = p_secret
            WHERE id = p_user_id AND totp_secret IS NULL
        $$;
        """
    )

    for signature in (
        "public.find_platform_admin(text)",
        "public.activation_set_password(uuid, text)",
        "public.activation_enroll_totp(uuid, text)",
    ):
        op.execute(f"ALTER FUNCTION {signature} OWNER TO {_DEFINER_ROLE}")
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.activation_enroll_totp(uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS public.activation_set_password(uuid, text)")
    op.execute("DROP FUNCTION IF EXISTS public.find_platform_admin(text)")
    op.execute(f"REVOKE SELECT, UPDATE ON public.users FROM {_DEFINER_ROLE}")
    op.execute("DROP INDEX IF EXISTS ux_users_platform_email")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS users_platform_admin_no_tenant")
    # No se restaura NOT NULL en downgrade: podría haber platform_admin con tenant nulo ya sembrados.

"""Migración perezosa bcrypt -> Argon2id para las cuentas reales importadas de SETEX.

`users.legacy_bcrypt_hash`: hash bcrypt heredado de la aplicación anterior de la asesoría real
Setex (`docs/export-migracion/2026-07-28/`), NULLABLE — solo existe durante la ventana de
migración. La app nueva verifica siempre con Argon2id (`identity/passwords.py`); en el primer login
de una cuenta importada sin `password_hash` todavía, `identity/service.py` comprueba la contraseña
contra este hash heredado y, si coincide, genera el Argon2id en ese mismo instante y limpia esta
columna (la contraseña en claro nunca se persiste, solo vive en memoria durante esa petición). Este
es el patrón estándar de migración de esquema de hash (mismo que usan Dropbox/Slack/WordPress),
propuesto y confirmado por Julio (dueño de los datos de origen) tras confirmar que un hash bcrypt no
es convertible a Argon2id sin la contraseña en texto plano.

`find_platform_admin` (login de plataforma) se sustituye (DROP+CREATE, precedente ya establecido en
0017 para `find_platform_admin_by_id`: no se puede añadir una columna de salida con `CREATE OR
REPLACE`) para devolver también `legacy_bcrypt_hash`.

`migrate_platform_admin_password`: la RLS de `users` (`tenant_id = current_setting('app.tenant_id')`)
no deja pasar NUNCA una fila con `tenant_id IS NULL` desde una sesión sin tenant (ni siquiera para
UPDATE del rol runtime, que no tiene bypassrls) — de ahí que la lectura de un `platform_admin` ya
pasara por `find_platform_admin`/`find_platform_admin_by_id` (SECURITY DEFINER). La escritura de la
migración perezosa necesita el mismo mecanismo: sin esta función, un `platform_admin` real
(`tech` de Setex) nunca podría completar su migración perezosa al hacer login desde el host de
plataforma.

No hace falta GRANT adicional sobre la tabla para el resto de tenants: el rol runtime
(`autoken_app`) ya tiene `SELECT, INSERT, UPDATE, DELETE` sobre toda `users` desde la migración base
(0001), que cubre la columna nueva vía `tenant_session` normal.

Revision ID: 0022_legacy_bcrypt_migration
Revises: 0021_invoice_edits_rotate_grant
Create Date: 2026-07-28
"""

from __future__ import annotations

from alembic import op

revision = "0022_legacy_bcrypt_migration"
down_revision = "0021_invoice_edits_rotate_grant"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute("ALTER TABLE public.users ADD COLUMN legacy_bcrypt_hash text")

    op.execute("DROP FUNCTION IF EXISTS public.find_platform_admin(text)")
    op.execute(
        """
        CREATE FUNCTION public.find_platform_admin(p_email text)
        RETURNS TABLE (
            id uuid, email text, role text, status text, password_hash text, totp_secret text,
            legacy_bcrypt_hash text
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            SELECT id, email, role, status, password_hash, totp_secret, legacy_bcrypt_hash
            FROM public.users
            WHERE email = p_email AND role = 'platform_admin' AND tenant_id IS NULL
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION public.find_platform_admin(text) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.find_platform_admin(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.find_platform_admin(text) TO {_APP_ROLE}")

    op.execute(
        """
        CREATE FUNCTION public.migrate_platform_admin_password(p_id uuid, p_password_hash text)
        RETURNS void
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            UPDATE public.users
                SET password_hash = p_password_hash, legacy_bcrypt_hash = NULL
                WHERE id = p_id AND role = 'platform_admin' AND tenant_id IS NULL
        $$;
        """
    )
    op.execute(
        f"ALTER FUNCTION public.migrate_platform_admin_password(uuid, text) OWNER TO {_DEFINER_ROLE}"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.migrate_platform_admin_password(uuid, text) FROM PUBLIC"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.migrate_platform_admin_password(uuid, text) "
        f"TO {_APP_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.migrate_platform_admin_password(uuid, text)")

    op.execute("DROP FUNCTION IF EXISTS public.find_platform_admin(text)")
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
    op.execute(f"ALTER FUNCTION public.find_platform_admin(text) OWNER TO {_DEFINER_ROLE}")
    op.execute("REVOKE ALL ON FUNCTION public.find_platform_admin(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.find_platform_admin(text) TO {_APP_ROLE}")

    op.execute("ALTER TABLE public.users DROP COLUMN legacy_bcrypt_hash")

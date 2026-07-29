"""Reseteo de contraseña de una cuenta ya activada (sin autoservicio de "olvidé mi contraseña").

`identity/activation.py` ya avisaba de este hueco al hablar de "reissue-activation": un token
perdido de una cuenta AÚN NO activada se reemite tal cual, pero una cuenta que ya fijó su
contraseña y quiere cambiarla no tenía ningún camino legítimo (el mismo problema que motivó la
migración 0023 para las altas). Esta migración añade una función `SECURITY DEFINER` más, mismo
patrón: borra `password_hash`/`totp_secret`/`legacy_bcrypt_hash` de una cuenta, devolviéndola al
estado "recién sembrada" (S1.3) para que `issue_activation_token` + `POST /auth/activate` le
permitan fijar una contraseña nueva desde cero, sin que esta pase nunca por el operador.

`reset_account_password(email, tenant_id)`: `tenant_id NULL` selecciona el ámbito de plataforma
(`platform_admin`), igual que `provision_platform_admin`/`revoke_platform_admin` (0023) — el mismo
email puede existir en ambos ámbitos a la vez (0003), así que el emparejamiento usa
`IS NOT DISTINCT FROM` para no confundirlos. Solo actúa si la cuenta YA tenía `password_hash`
fijado (si no, no hay nada que resetear: esa cuenta pendiente de activar usa `reissue-activation`,
no esta función) — de ahí que no haga falta ningún `INSERT`/`GRANT` nuevo: el definer ya tiene
`SELECT, UPDATE` sobre `users` desde 0003.

Revision ID: 0024_password_reset
Revises: 0023_account_provisioning
Create Date: 2026-07-29
"""

from __future__ import annotations

from alembic import op

revision = "0024_password_reset"
down_revision = "0023_account_provisioning"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION public.reset_account_password(p_email text, p_tenant_id uuid)
        RETURNS TABLE (id uuid)
        LANGUAGE sql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            UPDATE public.users
            SET password_hash = NULL, totp_secret = NULL, legacy_bcrypt_hash = NULL
            WHERE email = p_email
              AND tenant_id IS NOT DISTINCT FROM p_tenant_id
              AND password_hash IS NOT NULL
            RETURNING id
        $$;
        """
    )
    op.execute("ALTER FUNCTION public.reset_account_password(text, uuid) OWNER TO " + _DEFINER_ROLE)
    op.execute("REVOKE ALL ON FUNCTION public.reset_account_password(text, uuid) FROM PUBLIC")
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.reset_account_password(text, uuid) TO {_APP_ROLE}"
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.reset_account_password(text, uuid)")

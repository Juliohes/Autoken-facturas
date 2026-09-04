"""Auth: recuperación de contraseña autoservicio (`SECURITY DEFINER`).

PROMPT-AUTOFACTU-AUTH-COMPLETO.md bloque 1. No reutiliza `reset_account_password` (migración 0024):
esa función es el "reset por operador" (CLI `create_account.py reset-password`) y borra el TOTP a
propósito, para forzar re-enrolar el segundo factor cuando el operador actúa en nombre de otro. Aquí
es la propia persona quien restablece su contraseña olvidada: debe conservar su TOTP ya enrolado, si
lo tiene, así que el guard y el UPDATE son distintos (no toca `totp_secret`).

Mismo patrón que `activation_set_password` (migración 0003): dueño `autoken_definer` (BYPASSRLS,
NOLOGIN, no superusuario), `SET search_path` blindado, `REVOKE ALL FROM PUBLIC` + `GRANT EXECUTE`
al rol runtime. El guard `status = 'active' AND password_hash IS NOT NULL` es el inverso exacto del
de activación (esa cuenta aún no tiene contraseña; esta ya la tiene y quiere cambiarla) — así una
cuenta pendiente de aprobación o recién sembrada sin activar (sin contraseña todavía) no es
"restablecible": no tendría sentido "olvidar" una contraseña que nunca se llegó a fijar.

Revision ID: 0057_password_reset
Revises: 0056_r050_ctx
Create Date: 2026-09-02
"""

from __future__ import annotations

from alembic import op

revision = "0057_password_reset"
down_revision = "0056_r050_ctx"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"
_SIGNATURE = "public.password_reset_set_password(uuid, text)"


def upgrade() -> None:
    # password_reset_set_password: fija la contraseña SOLO si la cuenta es RESTABLECIBLE (activa y
    # YA tiene contraseña) y devuelve email/rol. El guard atómico del WHERE evita "restablecer" una
    # cuenta pendiente de aprobación o sin activar (password_hash IS NULL): no hay nada que olvidar
    # ahí, y sería una vía para saltarse la activación por token del operador. No toca totp_secret:
    # a diferencia del reset del operador (0024), la propia persona conserva su 2FA ya enrolado.
    op.execute(
        """
        CREATE FUNCTION public.password_reset_set_password(p_user_id uuid, p_hash text)
        RETURNS TABLE (id uuid, email text, role text)
        LANGUAGE sql
        VOLATILE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
            UPDATE public.users
            SET password_hash = p_hash
            WHERE id = p_user_id AND status = 'active' AND password_hash IS NOT NULL
            RETURNING id, email, role
        $$;
        """
    )
    op.execute(f"ALTER FUNCTION {_SIGNATURE} OWNER TO {_DEFINER_ROLE}")
    op.execute(f"REVOKE ALL ON FUNCTION {_SIGNATURE} FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION {_SIGNATURE} TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_SIGNATURE}")

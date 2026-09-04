"""Reduce round-trips de lecturas RLS del intake sin relajar el aislamiento."""

from __future__ import annotations

from alembic import op

revision = "0056_r050_ctx"
down_revision = "0055_r048_eta_definer_grants"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    """Fija el contexto local y ejecuta cada lectura bajo RLS en una única llamada SQL."""
    op.execute(
        """
        CREATE FUNCTION public.resolve_user_company_id_for_app(
            p_tenant_id uuid,
            p_user_id uuid
        ) RETURNS TABLE(id uuid)
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = public
        AS $function$
        BEGIN
            PERFORM set_config('app.tenant_id', p_tenant_id::text, true);
            RETURN QUERY
            SELECT c.id
            FROM memberships m
            JOIN companies c ON c.id = m.company_id
            WHERE m.user_id = p_user_id
              AND c.status = 'active';
        END;
        $function$
        """
    )
    op.execute(
        """
        CREATE FUNCTION public.find_duplicate_upload_id_for_app(
            p_tenant_id uuid,
            p_company_id uuid,
            p_uploaded_by uuid,
            p_sha256 text
        ) RETURNS uuid
        LANGUAGE plpgsql
        SECURITY INVOKER
        SET search_path = public
        AS $function$
        DECLARE
            duplicate_id uuid;
        BEGIN
            PERFORM set_config('app.tenant_id', p_tenant_id::text, true);
            PERFORM set_config('app.company_id', p_company_id::text, true);
            SELECT id
            INTO duplicate_id
            FROM uploaded_files
            WHERE company_id = p_company_id
              AND uploaded_by = p_uploaded_by
              AND sha256 = p_sha256
            LIMIT 1;
            RETURN duplicate_id;
        END;
        $function$
        """
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.resolve_user_company_id_for_app(uuid, uuid) TO {_APP_ROLE}"
    )
    op.execute(
        f"GRANT EXECUTE ON FUNCTION public.find_duplicate_upload_id_for_app(uuid, uuid, uuid, text) TO {_APP_ROLE}"
    )


def downgrade() -> None:
    """Retira las funciones y sus permisos explícitos."""
    op.execute(
        "REVOKE EXECUTE ON FUNCTION public.find_duplicate_upload_id_for_app(uuid, uuid, uuid, text) "
        f"FROM {_APP_ROLE}"
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION public.resolve_user_company_id_for_app(uuid, uuid) "
        f"FROM {_APP_ROLE}"
    )
    op.execute("DROP FUNCTION public.find_duplicate_upload_id_for_app(uuid, uuid, uuid, text)")
    op.execute("DROP FUNCTION public.resolve_user_company_id_for_app(uuid, uuid)")

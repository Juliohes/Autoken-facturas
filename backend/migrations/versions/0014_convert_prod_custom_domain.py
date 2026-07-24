"""`convert_tenant_to_production` devuelve `custom_domain` real (fix S4.6, auditoría arquitectura).

Hallazgo: `convert_tenant_to_production` (0011) nunca seleccionaba `custom_domain`, así que
`platform_admin.repository.TenantRecord.custom_domain` caía a su default `None` en la respuesta de
`POST /platform/tenants/{id}/convert-to-production` — no "campo sin rellenar" como en `create_tenant`
(ahí es correcto, un tenant recién creado nunca tuvo dominio propio), sino un valor **incorrecto**:
un tenant demo puede tener ya un `custom_domain` asignado (vía `PATCH .../custom-domain`, S4.6) antes
de convertirse a producción, y la respuesta mentiría (`custom_domain: null` cuando en BD sí hay uno).
Mismo `DROP`+`CREATE` que ya usó 0013 con `list_tenants()` (Postgres no permite ampliar el conjunto
de columnas de salida de una función vía `CREATE OR REPLACE`).

Revision ID: 0014_convert_prod_custom_domain
Revises: 0013_tenant_custom_domain
Create Date: 2026-07-24

Nota (auditoría de cobertura, hallazgo bloqueante corregido antes de mergear): el `revision` original
de este fichero (`0014_convert_to_production_custom_domain`, 40 caracteres) superaba el límite de
`alembic_version.version_num` (`varchar(32)`, default de Alembic sin override en `env.py`) — cualquier
`alembic upgrade head` real habría fallado con `StringDataRightTruncationError`, y con él toda la
suite de tests que aprovisiona BD (`provision_test_db()`). Acortado a ≤32 caracteres; ver el test
guardarraíl `test_migrations_revision_id_cabe_en_alembic_version` que impide que esto se repita.
"""

from __future__ import annotations

from alembic import op

revision = "0014_convert_prod_custom_domain"
down_revision = "0013_tenant_custom_domain"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"
_DEFINER_ROLE = "autoken_definer"


def upgrade() -> None:
    op.execute(f"REVOKE ALL ON FUNCTION public.convert_tenant_to_production(uuid) FROM {_APP_ROLE}")
    op.execute("DROP FUNCTION public.convert_tenant_to_production(uuid)")
    op.execute(
        """
        CREATE FUNCTION public.convert_tenant_to_production(p_tenant_id uuid)
        RETURNS TABLE (
            id uuid, slug text, name text, status text, is_demo boolean, created_at timestamptz,
            custom_domain text
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $$
        BEGIN
            UPDATE public.tenants AS t SET is_demo = false
                WHERE t.id = p_tenant_id AND t.is_demo = true;
            RETURN QUERY
                SELECT t.id, t.slug::text, t.name, t.status, t.is_demo, t.created_at,
                       t.custom_domain
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


def downgrade() -> None:
    op.execute(f"REVOKE ALL ON FUNCTION public.convert_tenant_to_production(uuid) FROM {_APP_ROLE}")
    op.execute("DROP FUNCTION public.convert_tenant_to_production(uuid)")
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

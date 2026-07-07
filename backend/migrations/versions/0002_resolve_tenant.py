"""Función `resolve_tenant(slug)` para el lookup subdominio->tenant pre-contexto (S1.2, issue #48).

La RLS de `tenants` (S1.1) aísla por su propio `id`, así que el rol runtime no puede leer un tenant
por `slug` sin tener ya su id. Esta función `SECURITY DEFINER` es el ÚNICO camino acotado para
resolver un subdominio a tenant antes de tener contexto: corre con los privilegios de su propietaria
(un rol que salta la RLS; superusuario en test/CI, rol owner con BYPASSRLS en prod, issue #50),
devuelve solo campos PÚBLICOS del tenant **activo** y no abre ninguna otra lectura de `tenants`.

`SET search_path = public` evita el secuestro por search_path (patrón anti-inyección obligatorio en
SECURITY DEFINER). Se revoca a PUBLIC y se concede EXECUTE solo al rol runtime.

Revision ID: 0002_resolve_tenant
Revises: 0001_tenancy_core_rls
Create Date: 2026-07-07
"""

from __future__ import annotations

from alembic import op

revision = "0002_resolve_tenant"
down_revision = "0001_tenancy_core_rls"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION public.resolve_tenant(p_slug text)
        RETURNS TABLE (id uuid, slug text, name text, is_demo boolean)
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
            SELECT id, slug, name, is_demo
            FROM public.tenants
            WHERE slug = p_slug AND status = 'active'
        $$;
        """
    )
    op.execute("REVOKE ALL ON FUNCTION public.resolve_tenant(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION public.resolve_tenant(text) TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.resolve_tenant(text)")

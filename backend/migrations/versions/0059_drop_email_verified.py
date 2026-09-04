"""Retira la verificación de email del registrante (a petición de Julio, 2026-09-03): se sustituye
por la decisión del admin por email (`identity.registration_decision`), sin ninguna columna nueva
-- reutiliza el mismo token de un solo uso en Redis que el resto de flujos de auth.

`email_verified_at` (migración 0058) queda sin ningún lector ni escritor tras este cambio: se
retira en vez de dejarla como columna muerta (mismo criterio de limpieza que el resto de la app).

Revision ID: 0059_drop_email_verified
Revises: 0058_email_verification
Create Date: 2026-09-03
"""

from __future__ import annotations

from alembic import op

revision = "0059_drop_email_verified"
down_revision = "0058_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.users DROP COLUMN IF EXISTS email_verified_at")


def downgrade() -> None:
    op.execute("ALTER TABLE public.users ADD COLUMN email_verified_at timestamptz")

"""Verificación del email del registrante (PROMPT-AUTOFACTU-AUTH-COMPLETO bloque 2).

`email_verified_at` (nullable, `NULL` = sin verificar) en vez de un booleano: registra CUÁNDO se
verificó, no solo si, sin coste adicional (mismo criterio que `confirmed_at` en `invoices`). No
bloquea la aprobación del admin (spec explícita del prompt): es solo información añadida al listado
de `GET /registrations`, así que no hace falta ningún CHECK ni migrar filas existentes (todas las
filas ya sembradas quedan `NULL` = no verificado, lo correcto: nunca pasaron por este flujo).

No hace falta ninguna función `SECURITY DEFINER` nueva: el `UPDATE` que marca el email como
verificado corre dentro de la sesión de tenant ya abierta por `public_tenant_context` (mismo patrón
que `registration_repo.insert_pending_user`), la RLS ya acota la fila al tenant del token.

Revision ID: 0058_email_verification
Revises: 0057_password_reset
Create Date: 2026-09-02
"""

from __future__ import annotations

from alembic import op

revision = "0058_email_verification"
down_revision = "0057_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE public.users ADD COLUMN email_verified_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE public.users DROP COLUMN IF EXISTS email_verified_at")

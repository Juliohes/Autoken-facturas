"""Concede UPDATE acotado a 2 columnas de `invoice_edits` para la rotación de clave (S5.2 C9).

`invoice_edits` es append-only por diseño desde su creación (migración 0008): el rol runtime solo
tenía `SELECT, INSERT`, igual que `ocr_corrections`/`audit_log` — ninguna fila se puede modificar
una vez escrita, ni siquiera por la propia aplicación.

La rotación de la clave maestra (S5.2 C9, `jobs.key_rotation`) necesita re-cifrar
`old_value`/`new_value` cuando el campo editado es sensible (`SENSITIVE_EDIT_FIELDS`): el valor
LÓGICO no cambia (sigue siendo el mismo CIF/nombre auditado), solo el ciphertext que lo protege. Al
intentarlo con el grant original, `UPDATE invoice_edits SET old_value = ..., new_value = ...`
fallaba con `InsufficientPrivilegeError` (hallazgo real durante las pruebas de esta tarea, no solo
teórico).

La solución NO es conceder `UPDATE` de la tabla completa (eso sí rompería el append-only real: la
aplicación podría entonces reescribir `field`/`edited_by`/`edited_at`/`tenant_id`/`company_id`/
`invoice_id` de una fila ya auditada). Postgres permite un grant de `UPDATE` **acotado a columnas
concretas**: se concede solo sobre `old_value`/`new_value`, las dos únicas columnas que la rotación
toca. El resto de la fila (quién editó qué y cuándo) sigue siendo inmutable de verdad.

Nota: un `SELECT ... FOR UPDATE` (bloqueo de fila) SÍ exige `UPDATE` de la fila completa en
Postgres, no basta un grant por columnas — por eso `jobs.key_rotation._rotate_invoice_edits` NO usa
`FOR UPDATE` en su `SELECT` (a diferencia de las otras 4 tablas cifradas, que sí tienen `UPDATE`
completo concedido desde sus migraciones originales); ver su docstring para el detalle.

Revision ID: 0021_invoice_edits_rotate_grant
Revises: 0020_encrypt_pii_at_rest
Create Date: 2026-07-26
"""

from __future__ import annotations

from alembic import op

revision = "0021_invoice_edits_rotate_grant"
down_revision = "0020_encrypt_pii_at_rest"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    op.execute(f"GRANT UPDATE (old_value, new_value) ON invoice_edits TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (old_value, new_value) ON invoice_edits FROM {_APP_ROLE}")

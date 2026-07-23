"""Purga de facturas de prueba (S3.5): grants de borrado sobre `invoices`/`uploaded_files`.

Hasta esta migración el rol runtime nunca tuvo `DELETE` sobre `invoices` (0007: SELECT, INSERT;
0008: + UPDATE) ni sobre `uploaded_files` (0004: SELECT, INSERT; 0005: + UPDATE (status)): ninguna
tarea hasta ahora borraba facturas de verdad. La purga de facturas `is_test=true` (spec S3.5) es la
primera vez que se borra: borrar la fila de `invoices` arrastra en cascada (ya declarado en el
esquema, 0007/0008) sus `invoice_tax_lines`/`ocr_corrections`/`invoice_edits`, sin necesitar grant
propio para esas tablas (la cascada la aplica el motor vía la restricción de clave foránea, no exige
privilegio de `DELETE` adicional al rol que ejecuta el `DELETE` en la tabla padre). El borrado de
`uploaded_files` es una sentencia aparte (no hay cascada en ese sentido: `invoices.uploaded_file_id`
apunta A `uploaded_files`, no al revés), de ahí el grant explícito.

Revision ID: 0009_purge_test_invoices
Revises: 0008_invoice_edits
Create Date: 2026-07-23
"""

from __future__ import annotations

from alembic import op

revision = "0009_purge_test_invoices"
down_revision = "0008_invoice_edits"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    op.execute(f"GRANT DELETE ON invoices TO {_APP_ROLE}")
    op.execute(f"GRANT DELETE ON uploaded_files TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE DELETE ON uploaded_files FROM {_APP_ROLE}")
    op.execute(f"REVOKE DELETE ON invoices FROM {_APP_ROLE}")

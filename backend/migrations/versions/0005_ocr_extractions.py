"""Extracción OCR (S2.3, ADR-0016): tabla `ocr_extractions` con RLS de dos niveles.

Crea la tabla de campos extraídos y validados de una factura, con RLS `FORCE` de dos niveles por
`app.tenant_id` + `app.company_id` (mismo patrón que `companies` en 0001 y `uploaded_files` en 0004),
UNIQUE `(uploaded_file_id)` para la extracción vigente única por fichero (idempotencia del reprocesado,
C10), FKs a tenants/companies/uploaded_files y grants mínimos al rol runtime (SELECT/INSERT/UPDATE: el
worker hace upsert). Además concede UPDATE sobre `uploaded_files` al rol runtime (0004 dejó solo
SELECT/INSERT): el worker transiciona el `status` del fichero (`ocr_done`/`needs_review`/`ocr_failed`).

Revision ID: 0005_ocr_extractions
Revises: 0004_intake_uploaded_files
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_ocr_extractions"
down_revision = "0004_intake_uploaded_files"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    op.create_table(
        "ocr_extractions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "uploaded_file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("total_amount", sa.Numeric(), nullable=True),
        sa.Column("net_amount", sa.Numeric(), nullable=True),
        sa.Column("tax_amount", sa.Numeric(), nullable=True),
        sa.Column("tax_lines", postgresql.JSONB(), nullable=False),
        sa.Column("counterparty_tax_id", sa.Text(), nullable=True),
        sa.Column("counterparty_name", sa.Text(), nullable=True),
        sa.Column("own_tax_id_present", sa.Boolean(), nullable=False),
        sa.Column("confidences", postgresql.JSONB(), nullable=False),
        sa.Column("validations", postgresql.JSONB(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        # `created_at` inmutable (primera extracción del fichero); `updated_at` se refresca en cada
        # reproceso (upsert por `uploaded_file_id`). Ver `ocr.repository._UPSERT`.
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("uploaded_file_id", name="ocr_extractions_uploaded_file_unique"),
    )

    # RLS FORCE de dos niveles (patrón EXACTO de `companies`/0001 y `uploaded_files`/0004, ADR-0001):
    # aislamiento por `app.tenant_id` + segundo nivel por `app.company_id`. `NULLIF(..., '')` hace que
    # un contexto vacío case a 0 filas (fail-closed). El `WITH CHECK` usa la MISMA expresión que el
    # `USING`, para que ninguna fila cruce la frontera de tenant ni de empresa al escribir (upsert).
    op.execute("ALTER TABLE ocr_extractions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ocr_extractions FORCE ROW LEVEL SECURITY")
    tenant_setting = "NULLIF(current_setting('app.tenant_id', true), '')"
    company_setting = "NULLIF(current_setting('app.company_id', true), '')"
    isolation = (
        f"tenant_id = {tenant_setting}::uuid "
        f"AND ({company_setting} IS NULL OR company_id = {company_setting}::uuid)"
    )
    op.execute(
        f"CREATE POLICY ocr_extractions_tenant_isolation ON ocr_extractions "
        f"USING ({isolation}) WITH CHECK ({isolation})"
    )

    # Grants mínimos al rol runtime: SELECT (lecturas de la pantalla de revisión) + INSERT + UPDATE
    # (el worker hace upsert por `uploaded_file_id` al reprocesar). Sin DELETE.
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ocr_extractions TO {_APP_ROLE}")
    # El worker transiciona SOLO el estado del fichero: 0004 dejó `uploaded_files` en SELECT/INSERT;
    # aquí se añade UPDATE **a nivel de columna** sobre `status` únicamente. Así el rol runtime NO
    # puede reescribir `sha256`/`storage_key`/`content_type` (preserva el append-only de esas columnas
    # que 0004 buscaba); solo mueve el estado (`ocr_done`/`needs_review`/`ocr_failed`).
    op.execute(f"GRANT UPDATE (status) ON uploaded_files TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(f"REVOKE UPDATE (status) ON uploaded_files FROM {_APP_ROLE}")
    op.execute("DROP POLICY IF EXISTS ocr_extractions_tenant_isolation ON ocr_extractions")
    op.drop_table("ocr_extractions")

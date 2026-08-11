"""Benchmark real de variante x motor (S6.7, spec
docs/specs/S6.7-benchmark-real-motor-variante.md, Área A): tabla `ocr_benchmark_results`.

Mismo patrón que `ocr_ranking_entries` (S4.8, migración 0019): una fila por `(uploaded_file_id,
variant, engine)`, no columnas fijas -- así 3 variantes x 6 motores caben sin migrar el esquema.
RLS de dos niveles idéntica al resto de tablas de OCR; `UniqueConstraint(uploaded_file_id, variant,
engine)` da la idempotencia del reprocesado (C4, upsert por combinación, nunca duplica).

A diferencia de `ocr_ranking_entries`/`ocr_comparison_runs` (S4.8/S2.10, que guardan el CIF/nombre
de contraparte EN CLARO dentro del JSONB `reading`, hallazgo pendiente documentado desde S4.8 §6),
esta tabla los cifra desde el día 1 (C23, decisión de alcance de esta tarea): `counterparty_tax_id`/
`counterparty_name` como columnas `bytea` dedicadas (mismo patrón ADR-0018 que
`invoices`/`companies` desde S5.2), fuera del JSONB `reading` (que solo lleva fechas, importes,
tramos de IVA y número de factura, sin ningún dato de identidad de la contraparte).

`model`/`counterparty_tax_id`/`counterparty_name`/`reading`/`tax_lines_matched`/`duration_ms` son
NULLABLE a propósito: una combinación caída (C2, motor sin respuesta) persiste una fila con esos
campos vacíos y `error` relleno, nunca al revés -- el motor de ejecución (`ocr.benchmark`) SIEMPRE
persiste una fila por combinación, con éxito o sin él.

Sin ninguna función `SECURITY DEFINER` de descubrimiento de candidatos ni de agregado todavía (spec,
fuera de alcance de esta parte de la tarea): eso llega con el panel de lote retroactivo (C10-C17) y
el ranking agregado (C18-C20), tareas posteriores.

Revision ID: 0029_ocr_benchmark_results
Revises: 0028_ocr_ranking_examples
Create Date: 2026-08-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0029_ocr_benchmark_results"
down_revision = "0028_ocr_ranking_examples"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    op.create_table(
        "ocr_benchmark_results",
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
        sa.Column("variant", sa.Text(), nullable=False),
        sa.Column("engine", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("counterparty_tax_id", postgresql.BYTEA(), nullable=True),
        sa.Column("counterparty_name", postgresql.BYTEA(), nullable=True),
        sa.Column("reading", postgresql.JSONB(), nullable=True),
        sa.Column("field_results", postgresql.JSONB(), nullable=False),
        sa.Column("tax_lines_matched", sa.Boolean(), nullable=True),
        sa.Column("aciertos", sa.Integer(), nullable=False),
        sa.Column("comparables", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint(
            "uploaded_file_id",
            "variant",
            "engine",
            name="ocr_benchmark_results_file_variant_engine_unique",
        ),
    )

    op.execute("ALTER TABLE ocr_benchmark_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ocr_benchmark_results FORCE ROW LEVEL SECURITY")
    tenant_setting = "NULLIF(current_setting('app.tenant_id', true), '')"
    company_setting = "NULLIF(current_setting('app.company_id', true), '')"
    isolation = (
        f"tenant_id = {tenant_setting}::uuid "
        f"AND ({company_setting} IS NULL OR company_id = {company_setting}::uuid)"
    )
    op.execute(
        f"CREATE POLICY ocr_benchmark_results_tenant_isolation ON ocr_benchmark_results "
        f"USING ({isolation}) WITH CHECK ({isolation})"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON ocr_benchmark_results TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS ocr_benchmark_results_tenant_isolation ON ocr_benchmark_results"
    )
    op.drop_table("ocr_benchmark_results")

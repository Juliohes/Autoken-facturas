"""Intake seguro de ficheros (S2.1, ADR-0015): tabla `uploaded_files` con RLS por tenant.

Crea la tabla de ficheros de intake, con RLS `FORCE` por `app.tenant_id` (mismo patrón que el núcleo
de tenancy, migración 0001), UNIQUE `(company_id, sha256)` para la no-duplicación por empresa
resistente a concurrencia (C14), FKs a companies/users/tenants y grants mínimos al rol runtime
(SELECT/INSERT: el intake no actualiza ni borra registros). El objeto vive en MinIO (bucket por
tenant); aquí solo el registro con su ubicación (`storage_bucket`/`storage_key`).

Revision ID: 0004_intake_uploaded_files
Revises: 0003_auth_platform_admin
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_intake_uploaded_files"
down_revision = "0003_auth_platform_admin"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    op.create_table(
        "uploaded_files",
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
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("storage_bucket", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_ocr"),
        sa.Column("scan_status", sa.Text(), nullable=False, server_default="clean"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("company_id", "sha256", name="uploaded_files_company_sha256_unique"),
    )
    op.create_index("ix_uploaded_files_tenant", "uploaded_files", ["tenant_id", "id"])

    # RLS FORCE de dos niveles (mismo patrón que `companies` en 0001, ADR-0001): aislamiento por
    # `app.tenant_id` + segundo nivel por `app.company_id`. `NULLIF(..., '')` hace que un contexto
    # vacío case a 0 filas (fail-closed) en vez de reventar el cast; el `company_id` sin fijar
    # (contexto de asesoría del `tenant_admin`) deja ver todo el tenant. El `WITH CHECK` usa la MISMA
    # expresión que el `USING`, para que ninguna fila cruce la frontera de tenant ni de empresa.
    op.execute("ALTER TABLE uploaded_files ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE uploaded_files FORCE ROW LEVEL SECURITY")
    tenant_setting = "NULLIF(current_setting('app.tenant_id', true), '')"
    company_setting = "NULLIF(current_setting('app.company_id', true), '')"
    isolation = (
        f"tenant_id = {tenant_setting}::uuid "
        f"AND ({company_setting} IS NULL OR company_id = {company_setting}::uuid)"
    )
    op.execute(
        f"CREATE POLICY uploaded_files_tenant_isolation ON uploaded_files "
        f"USING ({isolation}) WITH CHECK ({isolation})"
    )

    # Grants mínimos al rol runtime: SELECT (dedup, lecturas) + INSERT (alta). El intake no actualiza
    # ni borra registros; UPDATE/DELETE quedan fuera (append-only de facto para el rol de la app).
    op.execute(f"GRANT SELECT, INSERT ON uploaded_files TO {_APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS uploaded_files_tenant_isolation ON uploaded_files")
    op.drop_index("ix_uploaded_files_tenant", table_name="uploaded_files")
    op.drop_table("uploaded_files")

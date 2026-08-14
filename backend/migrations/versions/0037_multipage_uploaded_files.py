"""Páginas secundarias de un documento de intake (S6.12).

La fila existente de ``uploaded_files`` sigue siendo la raíz estable del documento y de todas las
FK existentes. Cada hoja adicional vive en esta tabla, ordenada y ligada a esa raíz.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0037_multipage_uploaded_files"
down_revision = "0036_manual_confirmation_cif"
branch_labels = None
depends_on = None

_APP_ROLE = "autoken_app"


def upgrade() -> None:
    op.create_table(
        "uploaded_file_pages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "root_uploaded_file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("uploaded_files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.SmallInteger(), nullable=False),
        sa.Column("storage_bucket", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "page_number BETWEEN 2 AND 5", name="uploaded_file_pages_page_number_check"
        ),
        sa.UniqueConstraint(
            "root_uploaded_file_id", "page_number", name="uploaded_file_pages_root_number_unique"
        ),
        sa.UniqueConstraint(
            "company_id", "sha256", name="uploaded_file_pages_company_sha256_unique"
        ),
    )
    op.create_index(
        "ix_uploaded_file_pages_root",
        "uploaded_file_pages",
        ["root_uploaded_file_id", "page_number"],
    )
    op.execute("ALTER TABLE uploaded_file_pages ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE uploaded_file_pages FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY uploaded_file_pages_root_isolation ON uploaded_file_pages "
        "USING (EXISTS (SELECT 1 FROM uploaded_files root "
        "WHERE root.id = root_uploaded_file_id)) "
        "WITH CHECK (EXISTS (SELECT 1 FROM uploaded_files root "
        "WHERE root.id = root_uploaded_file_id AND root.company_id = company_id))"
    )
    op.execute(f"GRANT SELECT, INSERT ON uploaded_file_pages TO {_APP_ROLE}")
    # Los UNIQUE de cada tabla no pueden impedir por sí solos que una página reutilice el hash de una
    # raíz. Este trigger toma el mismo advisory lock para ambos INSERT y comprueba la tabla hermana:
    # cierra también la carrera batch-vs-single sin depender de un pre-check de Python.
    op.execute(
        """
        CREATE FUNCTION public.ensure_uploaded_file_document_sha256_unique()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = public, pg_temp
        AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock(hashtextextended(NEW.company_id::text || ':' || NEW.sha256, 0));
            IF TG_TABLE_NAME = 'uploaded_files' THEN
                IF EXISTS (
                    SELECT 1 FROM uploaded_file_pages
                    WHERE company_id = NEW.company_id AND sha256 = NEW.sha256
                ) THEN
                    RAISE EXCEPTION 'hash ya presente en otro documento'
                    USING ERRCODE = 'unique_violation',
                          CONSTRAINT = 'uploaded_file_document_sha256_unique';
                END IF;
            ELSIF EXISTS (
                SELECT 1 FROM uploaded_files
                WHERE company_id = NEW.company_id AND sha256 = NEW.sha256
            ) THEN
                RAISE EXCEPTION 'hash ya presente en otro documento'
                USING ERRCODE = 'unique_violation',
                      CONSTRAINT = 'uploaded_file_document_sha256_unique';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER uploaded_files_document_sha256_unique "
        "BEFORE INSERT ON uploaded_files FOR EACH ROW "
        "EXECUTE FUNCTION ensure_uploaded_file_document_sha256_unique()"
    )
    op.execute(
        "CREATE TRIGGER uploaded_file_pages_document_sha256_unique "
        "BEFORE INSERT ON uploaded_file_pages FOR EACH ROW "
        "EXECUTE FUNCTION ensure_uploaded_file_document_sha256_unique()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS uploaded_file_pages_document_sha256_unique ON uploaded_file_pages")
    op.execute("DROP TRIGGER IF EXISTS uploaded_files_document_sha256_unique ON uploaded_files")
    op.execute("DROP FUNCTION IF EXISTS ensure_uploaded_file_document_sha256_unique()")
    op.execute("DROP POLICY IF EXISTS uploaded_file_pages_root_isolation ON uploaded_file_pages")
    op.drop_index("ix_uploaded_file_pages_root", table_name="uploaded_file_pages")
    op.drop_table("uploaded_file_pages")

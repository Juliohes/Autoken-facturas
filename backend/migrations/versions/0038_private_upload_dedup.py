"""Deduplicación de intake privada por usuario (S6.12).

Un mismo documento puede existir para dos cuentas `user` de una empresa sin que una reciba el id de
la otra en un 409. Las páginas secundarias guardan también su autor para que la garantía cubra todo
el documento y las carreras entre subida simple y lote.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0038_private_upload_dedup"
down_revision = "0037_multipage_uploaded_files"
branch_labels = None
depends_on = None


def _replace_document_hash_trigger(*, per_uploader: bool) -> None:
    if per_uploader:
        lock_key = "NEW.company_id::text || ':' || NEW.uploaded_by::text || ':' || NEW.sha256"
        predicate = (
            "company_id = NEW.company_id AND uploaded_by = NEW.uploaded_by AND sha256 = NEW.sha256"
        )
        constraint = "uploaded_file_document_uploader_sha256_unique"
    else:
        lock_key = "NEW.company_id::text || ':' || NEW.sha256"
        predicate = "company_id = NEW.company_id AND sha256 = NEW.sha256"
        constraint = "uploaded_file_document_sha256_unique"
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION public.ensure_uploaded_file_document_sha256_unique()
        RETURNS trigger
        LANGUAGE plpgsql
        SET search_path = public, pg_temp
        AS $$
        BEGIN
            PERFORM pg_advisory_xact_lock(hashtextextended({lock_key}, 0));
            IF TG_TABLE_NAME = 'uploaded_files' THEN
                IF EXISTS (SELECT 1 FROM uploaded_file_pages WHERE {predicate}) THEN
                    RAISE EXCEPTION 'hash ya presente en otro documento'
                    USING ERRCODE = 'unique_violation', CONSTRAINT = '{constraint}';
                END IF;
            ELSIF EXISTS (SELECT 1 FROM uploaded_files WHERE {predicate}) THEN
                RAISE EXCEPTION 'hash ya presente en otro documento'
                USING ERRCODE = 'unique_violation', CONSTRAINT = '{constraint}';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )


def upgrade() -> None:
    op.add_column(
        "uploaded_file_pages",
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    # Las páginas existentes son parte de su raíz: se hereda su autor antes de hacer la columna
    # obligatoria, sin perder documentos ya aceptados.
    op.execute(
        "UPDATE uploaded_file_pages page SET uploaded_by = root.uploaded_by "
        "FROM uploaded_files root WHERE root.id = page.root_uploaded_file_id"
    )
    op.alter_column("uploaded_file_pages", "uploaded_by", nullable=False)
    op.create_foreign_key(
        "uploaded_file_pages_uploaded_by_fkey",
        "uploaded_file_pages",
        "users",
        ["uploaded_by"],
        ["id"],
    )

    op.drop_constraint("uploaded_files_company_sha256_unique", "uploaded_files", type_="unique")
    op.create_unique_constraint(
        "uploaded_files_company_uploader_sha256_unique",
        "uploaded_files",
        ["company_id", "uploaded_by", "sha256"],
    )
    op.drop_constraint(
        "uploaded_file_pages_company_sha256_unique", "uploaded_file_pages", type_="unique"
    )
    op.create_unique_constraint(
        "uploaded_file_pages_company_uploader_sha256_unique",
        "uploaded_file_pages",
        ["company_id", "uploaded_by", "sha256"],
    )

    op.execute("DROP POLICY uploaded_file_pages_root_isolation ON uploaded_file_pages")
    op.execute(
        "CREATE POLICY uploaded_file_pages_root_isolation ON uploaded_file_pages "
        "USING (EXISTS (SELECT 1 FROM uploaded_files root WHERE root.id = root_uploaded_file_id)) "
        "WITH CHECK (EXISTS (SELECT 1 FROM uploaded_files root "
        "WHERE root.id = root_uploaded_file_id AND root.company_id = company_id "
        "AND root.uploaded_by = uploaded_by))"
    )
    _replace_document_hash_trigger(per_uploader=True)


def downgrade() -> None:
    _replace_document_hash_trigger(per_uploader=False)
    op.execute("DROP POLICY uploaded_file_pages_root_isolation ON uploaded_file_pages")
    op.execute(
        "CREATE POLICY uploaded_file_pages_root_isolation ON uploaded_file_pages "
        "USING (EXISTS (SELECT 1 FROM uploaded_files root WHERE root.id = root_uploaded_file_id)) "
        "WITH CHECK (EXISTS (SELECT 1 FROM uploaded_files root "
        "WHERE root.id = root_uploaded_file_id AND root.company_id = company_id))"
    )
    op.drop_constraint(
        "uploaded_file_pages_company_uploader_sha256_unique", "uploaded_file_pages", type_="unique"
    )
    op.create_unique_constraint(
        "uploaded_file_pages_company_sha256_unique", "uploaded_file_pages", ["company_id", "sha256"]
    )
    op.drop_constraint(
        "uploaded_files_company_uploader_sha256_unique", "uploaded_files", type_="unique"
    )
    op.create_unique_constraint(
        "uploaded_files_company_sha256_unique", "uploaded_files", ["company_id", "sha256"]
    )
    op.drop_constraint(
        "uploaded_file_pages_uploaded_by_fkey", "uploaded_file_pages", type_="foreignkey"
    )
    op.drop_column("uploaded_file_pages", "uploaded_by")

"""Modelo ORM del intake de ficheros (S2.1): `uploaded_files`.

El esquema aquí debe coincidir con la migración 0004 (el guard `alembic check` de CI detecta la
deriva ORM<->migración). Las políticas RLS y los grants viven en la migración (no se expresan en el
ORM), igual que en el núcleo de tenancy (`tenancy/models.py`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class UploadedFile(Base):
    """Fichero de intake subido, pendiente de procesar por el OCR (S2.3).

    Aislado por `tenant_id` (RLS S1.1) y por empresa destino `company_id`. La no-duplicación por
    empresa y cuenta que la subió la garantiza el UNIQUE `(company_id, uploaded_by, sha256)`
    (resistente a concurrencia, C14), sin revelar los documentos de un compañero.
    """

    __tablename__ = "uploaded_files"
    __table_args__ = (
        CheckConstraint(
            "direction IS NULL OR direction IN ('recibida', 'emitida')",
            name="uploaded_files_direction_check",
        ),
        CheckConstraint(
            "processing_stage IS NULL OR processing_stage IN "
            "('queued', 'loading_document', 'primary_ocr', 'validating', 'fallback_ocr', "
            "'consensus', 'persisting')",
            name="uploaded_files_processing_stage_check",
        ),
        UniqueConstraint(
            "company_id",
            "uploaded_by",
            "sha256",
            name="uploaded_files_company_uploader_sha256_unique",
        ),
        Index("ix_uploaded_files_tenant", "tenant_id", "id"),
        Index(
            "ix_uploaded_files_ocr_recovery",
            "status",
            "ocr_claim_expires_at",
            "ocr_recovery_enqueued_at",
        ),
        Index(
            "ix_uploaded_files_capture_session",
            "tenant_id",
            "uploaded_by",
            "capture_session_id",
            "capture_sequence",
            postgresql_where="capture_session_id IS NOT NULL",
        ),
        CheckConstraint(
            "((capture_session_id IS NULL AND capture_sequence IS NULL) OR "
            "(capture_session_id IS NOT NULL AND capture_sequence BETWEEN 1 AND 50))",
            name="uploaded_files_capture_session_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    storage_bucket: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending_ocr")
    processing_stage: Mapped[str | None] = mapped_column(
        Text, nullable=True, server_default="queued"
    )
    ocr_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ocr_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    capture_session_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    capture_sequence: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    ocr_claim_token: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    ocr_claim_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ocr_recovery_enqueued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scan_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="clean")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UploadedFilePage(Base):
    """Hoja adicional ordenada de un documento cuyo ancla es ``UploadedFile`` (S6.12)."""

    __tablename__ = "uploaded_file_pages"
    __table_args__ = (
        CheckConstraint(
            "page_number BETWEEN 2 AND 5", name="uploaded_file_pages_page_number_check"
        ),
        UniqueConstraint(
            "root_uploaded_file_id", "page_number", name="uploaded_file_pages_root_number_unique"
        ),
        UniqueConstraint(
            "company_id",
            "uploaded_by",
            "sha256",
            name="uploaded_file_pages_company_uploader_sha256_unique",
        ),
        Index("ix_uploaded_file_pages_root", "root_uploaded_file_id", "page_number"),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    root_uploaded_file_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    storage_bucket: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)

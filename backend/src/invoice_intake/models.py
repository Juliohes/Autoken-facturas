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
    DateTime,
    ForeignKey,
    Index,
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
    empresa la garantiza el UNIQUE `(company_id, sha256)` (resistente a concurrencia, C14).
    """

    __tablename__ = "uploaded_files"
    __table_args__ = (
        UniqueConstraint("company_id", "sha256", name="uploaded_files_company_sha256_unique"),
        Index("ix_uploaded_files_tenant", "tenant_id", "id"),
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
    scan_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="clean")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

"""Modelo ORM de la extracción OCR (S2.3): `ocr_extractions`.

El esquema aquí debe coincidir con la migración 0005 (el guard `alembic check` de CI detecta la
deriva ORM<->migración). Las políticas RLS de dos niveles y los grants viven en la migración, no en
el ORM, igual que en `uploaded_files` (0004) y el núcleo de tenancy (0001).

Una fila vigente por `uploaded_file_id` (UNIQUE): reprocesar hace upsert, no duplica (idempotencia).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class OcrExtraction(Base):
    """Campos extraídos y validados de una factura, ligados a su `uploaded_file`.

    Aislada por `tenant_id` (RLS S1.1) y por empresa `company_id` (segundo nivel). El estado global
    (`auto_ok`/`needs_review`) enruta la factura a confirmación directa o a revisión (S2.4).
    """

    __tablename__ = "ocr_extractions"
    __table_args__ = (
        UniqueConstraint("uploaded_file_id", name="ocr_extractions_uploaded_file_unique"),
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
    uploaded_file_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False
    )
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    tax_lines: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    counterparty_tax_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    counterparty_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    own_tax_id_present: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    validations: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    # `created_at` es INMUTABLE (primera extracción del fichero); `updated_at` se refresca en cada
    # reproceso (upsert). El reprocesado idempotente (C10) no miente la fecha de creación.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

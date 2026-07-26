"""Modelos ORM de la persistencia de facturas: invoices + tax_lines + ocr_corrections (S2.5) +
invoice_edits (S3.3).

El esquema aquí debe coincidir con las migraciones 0007/0008 + su enmienda de cifrado en la 0020
(S5.2; el guard `alembic check` de CI detecta la deriva ORM<->migración). Las políticas RLS de dos
niveles y los grants viven en la migración, no en el ORM, igual que en `uploaded_files` (0004) y
`ocr_extractions` (0005).

Una factura vigente por `uploaded_file_id` (UNIQUE): reconfirmar es 409, no duplica.
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
    text,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class Invoice(Base):
    """Factura contable persistida al confirmar (S2.5).

    Aislada por `tenant_id` (RLS S1.1) y por empresa `company_id` (segundo nivel). Guarda el
    veredicto del CIF de contraparte (`counterparty_cif_status`, S2.8), el aviso de descuadre
    (`balance_ok`) y el `snapshot` de lo confirmado (datos + aceptación) para la trazabilidad.
    """

    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("uploaded_file_id", name="invoices_uploaded_file_unique"),)

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
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # `counterparty_tax_id`/`counterparty_name` viven cifrados desde S5.2 (`pgp_sym_encrypt`); NULL
    # se conserva tal cual (anti-alucinación: contraparte no legible). El ORM nunca los lee/escribe
    # directamente (SQL crudo en `invoicing.repository`); `counterparty_tax_id_blind_index`
    # sustituye al filtro `ILIKE` retirado del panel (spec S5.2 C5).
    counterparty_tax_id: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    counterparty_tax_id_blind_index: Mapped[str | None] = mapped_column(Text, nullable=True)
    counterparty_name: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    counterparty_cif_status: Mapped[str] = mapped_column(Text, nullable=False)
    net_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    irpf_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    balance_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    confirmed_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InvoiceTaxLine(Base):
    """Un tramo de IVA confirmado de una factura (`invoice_tax_lines`)."""

    __tablename__ = "invoice_tax_lines"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    invoice_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    iva_pct: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    base: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    cuota: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)


class OcrCorrection(Base):
    """Corrección humana de un campo del OCR (`ocr_corrections`): dataset de mejora continua (S2.5).

    Una fila por campo cuyo valor confirmado difiere del que persistió el OCR (S2.3). `ai_value` es
    lo que leyó la IA; `human_value` lo que confirmó el humano (ambos como texto).
    """

    __tablename__ = "ocr_corrections"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    invoice_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_file_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(Text, nullable=False)
    ai_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    corrected_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class InvoiceEdit(Base):
    """Edición humana de un campo de una factura ya confirmada (`invoice_edits`, S3.3).

    Una fila por campo que cambió en una edición (no una fila por edición). Mismo patrón de diff que
    `OcrCorrection`, pero humano-vs-humano (post-confirmación), no IA-vs-humano (al confirmar):
    `old_value` es el valor anterior, `new_value` el editado, ambos como texto.
    """

    __tablename__ = "invoice_edits"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    invoice_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

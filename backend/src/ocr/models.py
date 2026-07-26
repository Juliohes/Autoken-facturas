"""Modelo ORM de la extracción OCR (S2.3): `ocr_extractions`.

El esquema aquí debe coincidir con la migración 0005 + su enmienda de cifrado en la 0020 (S5.2; el
guard `alembic check` de CI detecta la deriva ORM<->migración). Las políticas RLS de dos niveles y
los grants viven en la migración, no en el ORM, igual que en `uploaded_files` (0004) y el núcleo de
tenancy (0001).

Una fila vigente por `uploaded_file_id` (UNIQUE): reprocesar hace upsert, no duplica (idempotencia).

`OcrComparisonRun`/`OcrRankingEntry` (S2.10/S4.8) quedan FUERA del alcance de S5.2: sus columnas
`reading`/`original_reading`/`enhanced_reading` (JSONB) pueden llevar el CIF/nombre de contraparte
en claro dentro del blob serializado. Detrás de `platform_settings.ocr_experiment_enabled` (apagado
por defecto); ver seguimiento en el cierre de S5.2 antes de activar el experimento en producción.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import BYTEA, JSONB
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
    # Cifrados desde S5.2 (`pgp_sym_encrypt`), sin índice ciego (lectura cruda del OCR antes de
    # confirmar, sin ningún UNIQUE ni comparación por igualdad). El ORM nunca los lee/escribe
    # directamente (SQL crudo en `ocr.repository`).
    counterparty_tax_id: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    counterparty_name: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
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


class OcrComparisonRun(Base):
    """Comparativa original-vs-realzada de una lectura OCR (S2.10), detrás del interruptor de S4.10.

    Una fila vigente por `uploaded_file_id` (UNIQUE, mismo patrón de idempotencia que
    `OcrExtraction`). Experimento de coste acotado en el tiempo: nunca decide el resultado que ve el
    usuario (eso lo sigue decidiendo `ocr_extractions`, la lectura original).
    """

    __tablename__ = "ocr_comparison_runs"
    __table_args__ = (
        UniqueConstraint("uploaded_file_id", name="ocr_comparison_runs_uploaded_file_unique"),
        CheckConstraint(
            "winner IN ('original', 'enhanced', 'tie')", name="ocr_comparison_runs_winner_valid"
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
    uploaded_file_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False
    )
    original_reading: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    enhanced_reading: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    original_score: Mapped[int] = mapped_column(Integer, nullable=False)
    enhanced_score: Mapped[int] = mapped_column(Integer, nullable=False)
    winner: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OcrRankingEntry(Base):
    """Lectura de UN motor candidato sobre UNA factura, para el ranking multi-modelo (S4.8).

    Generaliza `OcrComparisonRun` (S2.10, 2 lecturas fijas) a N motores: una fila por
    `(uploaded_file_id, engine)` en vez de una fila por fichero con columnas fijas. Detrás del mismo
    interruptor `platform_settings.ocr_experiment_enabled`; nunca decide el resultado que ve el
    usuario (eso lo sigue decidiendo `ocr_extractions`, la lectura de producción).
    """

    __tablename__ = "ocr_ranking_entries"
    __table_args__ = (
        UniqueConstraint(
            "uploaded_file_id", "engine", name="ocr_ranking_entries_file_engine_unique"
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
    uploaded_file_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("uploaded_files.id", ondelete="CASCADE"), nullable=False
    )
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    reading: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

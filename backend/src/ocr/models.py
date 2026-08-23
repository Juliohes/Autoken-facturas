"""Modelo ORM de la extracción OCR (S2.3): `ocr_extractions`.

El esquema aquí debe coincidir con la migración 0005 + su enmienda de cifrado en la 0020 (S5.2; el
guard `alembic check` de CI detecta la deriva ORM<->migración). Las políticas RLS de dos niveles y
los grants viven en la migración, no en el ORM, igual que en `uploaded_files` (0004) y el núcleo de
tenancy (0001).

Una fila vigente por `uploaded_file_id` (UNIQUE): reprocesar hace upsert, no duplica (idempotencia).

`OcrComparisonRun`/`OcrRankingEntry` (S2.10/S4.8) cifran desde S6.7 C24 el CIF/nombre de contraparte
en columnas `bytea` dedicadas (mismo patrón ADR-0018 que `OcrBenchmarkResult`), fuera del JSONB
`reading`/`original_reading`/`enhanced_reading` (que ya no los lleva, ver migración 0033). Detrás de
`platform_settings.ocr_experiment_enabled` (apagado por defecto).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
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
    (`auto_ok`/`needs_review`/`hard_fail` — S6.14: captura ilegible, la imagen es el problema)
    enruta la factura a confirmación directa, a revisión (S2.4) o a repetir la foto (S6.14 C7).
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
    irpf_rate: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    irpf_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    # Sin cifrar (S6.1 C7): mismo criterio que los importes/fecha, no es un dato de identidad.
    invoice_number: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class OcrRecoveryMetrics(Base):
    """Última instantánea global del recuperador OCR (S6.13), solo contadores sin PII."""

    __tablename__ = "ocr_recovery_metrics"
    __table_args__ = (CheckConstraint("id", name="ocr_recovery_metrics_singleton_check"),)

    id: Mapped[bool] = mapped_column(Boolean, primary_key=True, server_default="true")
    pending: Mapped[int] = mapped_column(BigInteger, nullable=False)
    processing: Mapped[int] = mapped_column(BigInteger, nullable=False)
    abandoned: Mapped[int] = mapped_column(BigInteger, nullable=False)
    failed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ready: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OcrProcessingSample(Base):
    """Muestra agregada de duración OCR para ETA, sin tenant ni identificadores de factura."""

    __tablename__ = "ocr_processing_samples"
    __table_args__ = (
        CheckConstraint(
            "page_count_bucket IN ('1', '2-5', '6-10', '11+')",
            name="ocr_processing_samples_page_bucket_check",
        ),
        CheckConstraint(
            "queue_wait_seconds >= 0", name="ocr_processing_samples_queue_wait_check"
        ),
        CheckConstraint(
            "processing_seconds >= 0", name="ocr_processing_samples_processing_check"
        ),
        Index(
            "ix_ocr_processing_samples_lookup",
            "engine",
            "model",
            "page_count_bucket",
            "completed_at",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    page_count_bucket: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    queue_wait_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    processing_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    completed_at: Mapped[datetime] = mapped_column(
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
    # Cifrados desde S6.7 C24 (`pgp_sym_encrypt`), fuera del JSONB de arriba; el ORM nunca los
    # lee/escribe directamente (SQL crudo en `ocr.comparison_repository`).
    original_counterparty_tax_id: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    original_counterparty_name: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    enhanced_counterparty_tax_id: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    enhanced_counterparty_name: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
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


class OcrBenchmarkResult(Base):
    """Fila de una combinación (variante, motor) del benchmark real S6.7: `ocr_benchmark_results`.

    El esquema aquí debe coincidir con la migración 0029 (el guard `alembic check` de CI detecta la
    deriva ORM<->migración -- 2026-08-11, S6.7 auditoría, hallazgo CRÍTICO: esta clase faltaba desde
    la migración 0029, igual patrón que `OcrRankingEntry`/`OcrComparisonRun`). Una fila vigente por
    `(uploaded_file_id, variant, engine)` (UNIQUE, idempotencia del reprocesado, C4).

    A diferencia de `OcrComparisonRun`/`OcrRankingEntry` (fuera de alcance de S5.2, CIF/nombre de
    contraparte en claro dentro del JSONB), esta tabla los cifra desde el día 1 (C23, ADR-0018):
    dos columnas `bytea` dedicadas, fuera del JSONB `reading` (que solo lleva fechas, importes,
    tramos de IVA y número de factura). El ORM nunca lee/escribe esas dos columnas directamente
    (SQL crudo en `ocr.benchmark_repository`, mismo patrón que `OcrExtraction`).
    """

    __tablename__ = "ocr_benchmark_results"
    __table_args__ = (
        UniqueConstraint(
            "uploaded_file_id",
            "variant",
            "engine",
            name="ocr_benchmark_results_file_variant_engine_unique",
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
    variant: Mapped[str] = mapped_column(Text, nullable=False)
    engine: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Cifrados desde el día 1 (C23, `pgp_sym_encrypt`); el ORM nunca los lee/escribe directamente.
    counterparty_tax_id: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    counterparty_name: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    reading: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    field_results: Mapped[list[Any]] = mapped_column(JSONB, nullable=False)
    tax_lines_matched: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    aciertos: Mapped[int] = mapped_column(Integer, nullable=False)
    comparables: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    benchmark_contract_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalization_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    ground_truth_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    variant_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    field_exact_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    critical_field_accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    all_critical_exact: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    arithmetic_valid: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    hallucination_flags: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    manual_corrections_per_invoice: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
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
    # Cifrados desde S6.7 C24 (`pgp_sym_encrypt`), fuera del JSONB de arriba; el ORM nunca los
    # lee/escribe directamente (SQL crudo en `ocr.ranking_repository`).
    counterparty_tax_id: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    counterparty_name: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

"""Modelos ORM de tablas operativas de plataforma (sin `tenant_id`/RLS).

`PlatformSettings` (S4.10, migración 0017): tabla de una sola fila (`id boolean PRIMARY KEY
DEFAULT true CHECK (id)`, garantiza que nunca pueda existir una segunda). El código de aplicación
no la toca directamente (siempre a través de las funciones `SECURITY DEFINER`
`get_platform_settings`/`set_platform_settings`, ver `settings_repository.py`).

`OcrBenchmarkBatchRun` (S6.7 Área C, migración 0030): progreso persistido del lote retroactivo del
benchmark real -- SIN `tenant_id`/RLS (no guarda ningún dato de tenant, solo el progreso agregado
de un lote lanzado por un `admin-tech`); se lee/escribe a través de funciones `SECURITY DEFINER`
(`platform_admin/benchmark_batch_repository.py`).

Ambos modelos existen solo para que el esquema declarado coincida con el de su migración (guard de
deriva ORM<->migración, CI) -- ningún repositorio los usa como ORM de escritura habitual (SQL/
funciones `SECURITY DEFINER` en su lugar, mismo criterio que `OcrExtraction`/`OcrBenchmarkResult`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"
    # Mismo `CHECK (id)` que declara la migración 0017 (nunca puede existir una segunda fila):
    # sin declararlo aquí, el guard de deriva ORM<->migración lo detecta como constraint de sobra.
    __table_args__ = (
        CheckConstraint("id", name="platform_settings_id_check"),
        CheckConstraint(
            "ocr_policy_version >= 1", name="platform_settings_ocr_policy_version_check"
        ),
        CheckConstraint(
            "ocr_consensus_mode IN ('primary_only', 'per_field')",
            name="platform_settings_ocr_policy_consensus_check",
        ),
        CheckConstraint(
            "(ocr_fallback_engine IS NULL AND ocr_fallback_model IS NULL) "
            "OR (ocr_fallback_engine IS NOT NULL AND ocr_fallback_model IS NOT NULL)",
            name="platform_settings_ocr_fallback_complete_check",
        ),
    )

    id: Mapped[bool] = mapped_column(Boolean, primary_key=True, server_default="true")
    ocr_experiment_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    ocr_policy_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    ocr_primary_engine: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="gemini-3.5-flash"
    )
    ocr_primary_model: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="gemini-3.5-flash"
    )
    ocr_fallback_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    ocr_fallback_engine: Mapped[str | None] = mapped_column(
        Text, nullable=True, server_default="mistral-ocr-4"
    )
    ocr_fallback_model: Mapped[str | None] = mapped_column(
        Text, nullable=True, server_default="mistral-ocr-4-0"
    )
    ocr_consensus_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="primary_only"
    )
    ocr_lab_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    ocr_auto_benchmark_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    ocr_benchmark_engines: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default='["tesseract"]'
    )
    ocr_benchmark_variants: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default='["original", "enhanced", "clahe"]'
    )


class OcrBenchmarkBatchRun(Base):
    __tablename__ = "ocr_benchmark_batch_runs"
    # Mismo `CHECK` que declara la migración 0030 (sin declararlo aquí, el guard de deriva
    # ORM<->migración lo detecta como constraint de sobra).
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'done', 'failed')",
            name="ocr_benchmark_batch_runs_status_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    completed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OcrPolicyPromotion(Base):
    __tablename__ = "ocr_policy_promotions"

    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    actor_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    old_policy: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    new_policy: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    promoted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OcrBenchmarkBatchCandidate(Base):
    """Snapshot inmutable de los documentos elegidos al crear un lote S6.7."""

    __tablename__ = "ocr_benchmark_batch_candidates"

    batch_run_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("ocr_benchmark_batch_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    uploaded_file_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    company_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)

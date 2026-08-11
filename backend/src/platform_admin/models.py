"""Modelos ORM de tablas operativas de plataforma (sin `tenant_id`/RLS).

`PlatformSettings` (S4.10, migración 0017): tabla de una sola fila (`id boolean PRIMARY KEY
DEFAULT true CHECK (id)`, garantiza que nunca pueda existir una segunda). El código de aplicación
no la toca directamente (siempre a través de las funciones `SECURITY DEFINER`
`get_platform_settings`/`set_platform_settings`, ver `settings_repository.py`).

`OcrBenchmarkBatchRun` (S6.7 Área C, migración 0030): progreso persistido del lote retroactivo del
benchmark real -- SIN `tenant_id`/RLS (no guarda ningún dato de tenant, solo el progreso agregado
de un lote lanzado por un `admin-tech`); se lee/escribe directamente con `identity.session`
(`platform_admin/benchmark_batch_repository.py`), nunca por una función `SECURITY DEFINER`.

Ambos modelos existen solo para que el esquema declarado coincida con el de su migración (guard de
deriva ORM<->migración, CI) -- ningún repositorio los usa como ORM de escritura habitual (SQL/
funciones `SECURITY DEFINER` en su lugar, mismo criterio que `OcrExtraction`/`OcrBenchmarkResult`).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class PlatformSettings(Base):
    __tablename__ = "platform_settings"
    # Mismo `CHECK (id)` que declara la migración 0017 (nunca puede existir una segunda fila):
    # sin declararlo aquí, el guard de deriva ORM<->migración lo detecta como constraint de sobra.
    __table_args__ = (CheckConstraint("id", name="platform_settings_id_check"),)

    id: Mapped[bool] = mapped_column(Boolean, primary_key=True, server_default="true")
    ocr_experiment_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
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

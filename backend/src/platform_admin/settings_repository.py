"""Acceso a datos del interruptor admin-tech (S4.10): llama a las funciones `SECURITY DEFINER`
`get_platform_settings`/`set_platform_settings` (migración 0017), único camino permitido para tocar
`platform_settings`. Ningún SQL directo sobre esa tabla desde aquí.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ocr.policy import OcrPolicy


@dataclass(frozen=True)
class PlatformSettings:
    """El único ajuste de plataforma hoy (S4.10): el interruptor que gobernará S2.9/S2.10/S4.8."""

    ocr_experiment_enabled: bool


@dataclass(frozen=True)
class OcrLabSettings:
    lab_visible: bool
    auto_benchmark_enabled: bool
    benchmark_engines: list[str]
    benchmark_variants: list[str]


@dataclass(frozen=True)
class OcrPolicyPromotion:
    id: UUID
    old_policy: dict[str, object]
    new_policy: dict[str, object]
    actor_id: UUID
    promoted_at: datetime


async def get_ocr_policy(session: AsyncSession) -> OcrPolicy:
    """Lee la política persistida, sin consultar configuración del laboratorio."""
    row = (await session.execute(text("SELECT * FROM get_ocr_policy()"))).one()
    return OcrPolicy(
        version=row.version,
        primary_engine=row.primary_engine,
        primary_model=row.primary_model,
        fallback_enabled=row.fallback_enabled,
        fallback_engine=row.fallback_engine,
        fallback_model=row.fallback_model,
        consensus_mode=row.consensus_mode,
    )


async def set_ocr_policy(session: AsyncSession, policy: OcrPolicy) -> OcrPolicy:
    """Guarda una política ya validada por Pydantic y devuelve el snapshot confirmado."""
    row = (
        await session.execute(
            text(
                "SELECT * FROM set_ocr_policy(:version, :primary_engine, :primary_model, "
                ":fallback_enabled, :fallback_engine, :fallback_model, :consensus_mode)"
            ),
            {
                "version": policy.version,
                "primary_engine": policy.primary_engine,
                "primary_model": policy.primary_model,
                "fallback_enabled": policy.fallback_enabled,
                "fallback_engine": policy.fallback_engine,
                "fallback_model": policy.fallback_model,
                "consensus_mode": policy.consensus_mode,
            },
        )
    ).one()
    return OcrPolicy(
        version=row.version,
        primary_engine=row.primary_engine,
        primary_model=row.primary_model,
        fallback_enabled=row.fallback_enabled,
        fallback_engine=row.fallback_engine,
        fallback_model=row.fallback_model,
        consensus_mode=row.consensus_mode,
    )


async def get_settings(session: AsyncSession) -> PlatformSettings:
    """Estado actual del interruptor (siempre hay una fila: la inserta la propia migración 0017)."""
    row = (
        await session.execute(text("SELECT ocr_experiment_enabled FROM get_platform_settings()"))
    ).one()
    return PlatformSettings(ocr_experiment_enabled=row.ocr_experiment_enabled)


async def set_settings(session: AsyncSession, *, ocr_experiment_enabled: bool) -> PlatformSettings:
    """Cambia el interruptor y devuelve el estado ya confirmado (idempotente: fijarlo al valor que
    ya tenía no es un error)."""
    row = (
        await session.execute(
            text("SELECT ocr_experiment_enabled FROM set_platform_settings(:enabled)"),
            {"enabled": ocr_experiment_enabled},
        )
    ).one()
    return PlatformSettings(ocr_experiment_enabled=row.ocr_experiment_enabled)


async def get_lab_settings(session: AsyncSession) -> OcrLabSettings:
    row = (await session.execute(text("SELECT * FROM get_ocr_lab_settings()"))).one()
    return OcrLabSettings(
        lab_visible=row.lab_visible,
        auto_benchmark_enabled=row.auto_benchmark_enabled,
        benchmark_engines=list(row.benchmark_engines),
        benchmark_variants=list(row.benchmark_variants),
    )


async def set_lab_settings(session: AsyncSession, settings: OcrLabSettings) -> OcrLabSettings:
    row = (
        await session.execute(
            text(
                "SELECT * FROM set_ocr_lab_settings(:visible, :enabled, "
                "CAST(:engines AS jsonb), CAST(:variants AS jsonb))"
            ),
            {
                "visible": settings.lab_visible,
                "enabled": settings.auto_benchmark_enabled,
                "engines": json.dumps(settings.benchmark_engines),
                "variants": json.dumps(settings.benchmark_variants),
            },
        )
    ).one()
    return OcrLabSettings(
        lab_visible=row.lab_visible,
        auto_benchmark_enabled=row.auto_benchmark_enabled,
        benchmark_engines=list(row.benchmark_engines),
        benchmark_variants=list(row.benchmark_variants),
    )


async def record_policy_promotion(
    session: AsyncSession,
    *,
    actor_id: UUID,
    old_policy: dict[str, object],
    new_policy: dict[str, object],
) -> OcrPolicyPromotion:
    row = (
        await session.execute(
            text(
                "INSERT INTO ocr_policy_promotions "
                "(actor_id, old_policy, new_policy) "
                "VALUES (:actor_id, CAST(:old_policy AS jsonb), CAST(:new_policy AS jsonb)) "
                "RETURNING id, old_policy, new_policy, actor_id, promoted_at"
            ),
            {
                "actor_id": str(actor_id),
                "old_policy": json.dumps(old_policy),
                "new_policy": json.dumps(new_policy),
            },
        )
    ).one()
    return OcrPolicyPromotion(
        id=row.id,
        old_policy=dict(row.old_policy),
        new_policy=dict(row.new_policy),
        actor_id=row.actor_id,
        promoted_at=row.promoted_at,
    )

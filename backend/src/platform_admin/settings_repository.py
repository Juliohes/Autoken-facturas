"""Acceso a datos del interruptor admin-tech (S4.10): llama a las funciones `SECURITY DEFINER`
`get_platform_settings`/`set_platform_settings` (migración 0017), único camino permitido para tocar
`platform_settings`. Ningún SQL directo sobre esa tabla desde aquí.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class PlatformSettings:
    """El único ajuste de plataforma hoy (S4.10): el interruptor que gobernará S2.9/S2.10/S4.8."""

    ocr_experiment_enabled: bool


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

"""Servicio del ranking multi-modelo (S4.8): passthrough sobre `ocr.ranking_repository`.

Capa fina entre el router HTTP y el repositorio (mismo patrón que `settings_service`, S4.10):
sitio natural para una regla de negocio futura sobre el agregado, sin acoplar el router al SQL.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ocr.ranking_repository import EngineRankingSummary, get_engine_summary

__all__ = ["get_ranking_summary"]


async def get_ranking_summary(session: AsyncSession) -> list[EngineRankingSummary]:
    return await get_engine_summary(session)

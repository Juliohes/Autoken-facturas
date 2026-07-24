"""Lógica de dominio del interruptor admin-tech (S4.10). Hoy es un passthrough deliberado: un único
booleano sin ninguna regla de negocio más allá de "existe siempre, se puede leer y escribir" — el
propio Pydantic del router ya valida el tipo del body. Se mantiene como capa aparte (en vez de que
el router llame directo al repositorio) por consistencia con el resto de `platform_admin`
(router fino -> service -> repository) y como sitio natural si en el futuro aparece una regla real
(p. ej. registrar quién lo cambió).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from platform_admin import settings_repository
from platform_admin.settings_repository import PlatformSettings


async def get_settings(session: AsyncSession) -> PlatformSettings:
    return await settings_repository.get_settings(session)


async def set_settings(session: AsyncSession, *, ocr_experiment_enabled: bool) -> PlatformSettings:
    return await settings_repository.set_settings(
        session, ocr_experiment_enabled=ocr_experiment_enabled
    )

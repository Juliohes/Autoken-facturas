"""Lógica de dominio del interruptor admin-tech (S4.10). Hoy es un passthrough deliberado: un único
booleano sin ninguna regla de negocio más allá de "existe siempre, se puede leer y escribir" — el
propio Pydantic del router ya valida el tipo del body. Se mantiene como capa aparte (en vez de que
el router llame directo al repositorio) por consistencia con el resto de `platform_admin`
(router fino -> service -> repository) y como sitio natural si en el futuro aparece una regla real
(p. ej. registrar quién lo cambió).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ocr.policy import OcrPolicy
from platform_admin import settings_repository
from platform_admin.settings_repository import OcrLabSettings, OcrPolicyPromotion, PlatformSettings


async def get_settings(session: AsyncSession) -> PlatformSettings:
    return await settings_repository.get_settings(session)


async def set_settings(session: AsyncSession, *, ocr_experiment_enabled: bool) -> PlatformSettings:
    return await settings_repository.set_settings(
        session, ocr_experiment_enabled=ocr_experiment_enabled
    )


async def get_ocr_policy(session: AsyncSession) -> OcrPolicy:
    return await settings_repository.get_ocr_policy(session)


async def set_ocr_policy(session: AsyncSession, policy: OcrPolicy) -> OcrPolicy:
    current = await settings_repository.get_ocr_policy(session)
    if policy.version <= current.version:
        raise ValueError("policy version debe aumentar")
    return await settings_repository.set_ocr_policy(session, policy)


async def get_lab_settings(session: AsyncSession) -> OcrLabSettings:
    return await settings_repository.get_lab_settings(session)


async def set_lab_settings(session: AsyncSession, settings: OcrLabSettings) -> OcrLabSettings:
    return await settings_repository.set_lab_settings(session, settings)


async def promote_ocr_policy(
    session: AsyncSession, *, actor_id: UUID, policy: OcrPolicy
) -> OcrPolicyPromotion:
    current = await settings_repository.get_ocr_policy(session)
    if policy.version <= current.version:
        raise ValueError("policy version debe aumentar")
    old_policy = current.model_dump()
    new_policy = policy.model_dump()
    await settings_repository.set_ocr_policy(session, policy)
    return await settings_repository.record_policy_promotion(
        session,
        actor_id=actor_id,
        old_policy=old_policy,
        new_policy=new_policy,
    )

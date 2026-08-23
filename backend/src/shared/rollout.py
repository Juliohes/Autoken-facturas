"""Resolución cerrada de flags de rollout R-051.

Los nombres son una allowlist de código, no claves arbitrarias de usuario. La allowlist de tenants
solo sirve para el canario y no se devuelve a ningún cliente.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from shared.config import Settings


class FeatureFlag(StrEnum):
    SCANNER_V2 = "scanner_v2_enabled"
    CONTINUOUS_CAPTURE = "continuous_capture_enabled"
    REVIEW_INBOX = "review_inbox_enabled"
    DRAFT_AUTOSAVE = "draft_autosave_enabled"
    PROCESSING_STAGES = "processing_stages_enabled"
    OCR_POLICY_V2 = "ocr_policy_v2_enabled"
    SUPPLIER_LEARNING = "supplier_learning_enabled"


def is_rollout_enabled(settings: Settings, flag: FeatureFlag, tenant_id: UUID) -> bool:
    """Devuelve si un flag está activo globalmente o para el tenant del canario."""
    if not bool(getattr(settings, flag.value, False)):
        return False
    allowlist = settings.rollout_tenant_allowlist
    return not allowlist or tenant_id in allowlist


def evaluated_feature_flags(settings: Settings, tenant_id: UUID | None) -> dict[str, bool]:
    """Devuelve solo flags evaluados, sin filtrar configuración de rollout al cliente."""
    if tenant_id is None:
        return {}
    return {flag.value: is_rollout_enabled(settings, flag, tenant_id) for flag in FeatureFlag}

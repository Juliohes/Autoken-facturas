"""Contrato puro de la política OCR de producción (R-033)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

ConsensusMode = Literal["primary_only", "per_field"]


class OcrPolicy(BaseModel):
    """Política versionada que decide qué motor puede usar producción."""

    version: int = Field(ge=1)
    primary_engine: str = Field(min_length=1)
    primary_model: str = Field(min_length=1)
    fallback_enabled: bool
    fallback_engine: str | None = None
    fallback_model: str | None = None
    consensus_mode: ConsensusMode

    @model_validator(mode="after")
    def validate_fallback(self) -> OcrPolicy:
        if self.fallback_enabled and (not self.fallback_engine or not self.fallback_model):
            raise ValueError("fallback requiere fallback_engine y fallback_model")
        if (self.fallback_engine is None) != (self.fallback_model is None):
            raise ValueError("fallback_engine y fallback_model deben aparecer juntos")
        return self


def legacy_policy(settings: Any) -> OcrPolicy:
    """Representa el OCR anterior a R-033 sin consultar la política persistida."""
    return OcrPolicy(
        version=1,
        primary_engine="gemini-3-flash",
        primary_model=settings.gemini_flash_model,
        fallback_enabled=False,
        consensus_mode="primary_only",
    )


__all__ = ["ConsensusMode", "OcrPolicy", "legacy_policy"]

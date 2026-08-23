"""Tests puros de la política OCR de producción R-033."""

from __future__ import annotations

from uuid import uuid4

import pytest

from jobs import ocr
from ocr.engines import production
from ocr.policy import OcrPolicy, legacy_policy


def test_r033_acepta_la_politica_provisional_recomendada() -> None:
    policy = OcrPolicy(
        version=1,
        primary_engine="gemini-3.5-flash",
        primary_model="gemini-3.5-flash",
        fallback_enabled=False,
        fallback_engine="mistral-ocr-4",
        fallback_model="mistral-ocr-4-0",
        consensus_mode="primary_only",
    )

    assert policy.primary_engine == "gemini-3.5-flash"
    assert policy.fallback_enabled is False


def test_r033_rechaza_fallback_activado_sin_motor_y_modelo() -> None:
    with pytest.raises(ValueError, match="fallback"):
        OcrPolicy(
            version=1,
            primary_engine="gemini-3.5-flash",
            primary_model="gemini-3.5-flash",
            fallback_enabled=True,
            fallback_engine=None,
            fallback_model=None,
            consensus_mode="primary_only",
        )


def test_r033_rechaza_modo_de_consenso_desconocido() -> None:
    with pytest.raises(ValueError, match="consensus_mode"):
        OcrPolicy(
            version=1,
            primary_engine="gemini-3.5-flash",
            primary_model="gemini-3.5-flash",
            fallback_enabled=False,
            fallback_engine=None,
            fallback_model=None,
            consensus_mode="winner_takes_all",
        )


def test_r033_el_factory_usa_el_modelo_primario_persistido(monkeypatch) -> None:
    observed: dict[str, str] = {}

    def build_gemini(_settings, *, engine: str, model: str):
        observed.update(engine=engine, model=model)
        return object()

    monkeypatch.setattr(production, "build_gemini_model_extractor", build_gemini)
    policy = OcrPolicy(
        version=3,
        primary_engine="gemini-3.6-flash",
        primary_model="modelo-fijado-por-admin",
        fallback_enabled=False,
        consensus_mode="primary_only",
    )

    production.build_production_extractor(object(), policy)

    assert observed == {
        "engine": "gemini-3.6-flash",
        "model": "modelo-fijado-por-admin",
    }


def test_legacy_policy_reproduce_el_ocr_anterior_sin_fallback() -> None:
    settings = type("Settings", (), {"gemini_flash_model": "gemini-3-flash-preview"})()

    policy = legacy_policy(settings)

    assert policy.model_dump() == {
        "version": 1,
        "primary_engine": "gemini-3-flash",
        "primary_model": "gemini-3-flash-preview",
        "fallback_enabled": False,
        "fallback_engine": None,
        "fallback_model": None,
        "consensus_mode": "primary_only",
    }


@pytest.mark.asyncio
async def test_rollout_ocr_policy_apagado_no_consulta_la_politica_persistida(monkeypatch) -> None:
    settings = type(
        "Settings",
        (),
        {
            "gemini_flash_model": "gemini-3-flash-preview",
            "ocr_policy_v2_enabled": False,
            "rollout_tenant_allowlist": [],
        },
    )()

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("no debe leer la política v2")

    monkeypatch.setattr(ocr.settings_repository, "get_ocr_policy", fail_if_called)

    policy = await ocr._get_production_policy(settings, object(), uuid4())

    assert policy.primary_engine == "gemini-3-flash"

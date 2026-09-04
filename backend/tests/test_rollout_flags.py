"""Pruebas puras del sistema cerrado de flags de rollout R-051."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from shared.rollout import FeatureFlag, evaluated_feature_flags, is_rollout_enabled


def _settings(**overrides: object) -> SimpleNamespace:
    values = {flag.value: True for flag in FeatureFlag}
    values["rollout_tenant_allowlist"] = []
    values.update(overrides)
    return SimpleNamespace(**values)


def test_flag_activo_sin_allowlist_se_aplica_a_todos_los_tenants() -> None:
    assert is_rollout_enabled(_settings(), FeatureFlag.SUPPLIER_LEARNING, uuid4())


def test_flag_activo_con_allowlist_solo_se_aplica_al_tenant_piloto() -> None:
    pilot = uuid4()
    settings = _settings(rollout_tenant_allowlist=[pilot])

    assert is_rollout_enabled(settings, FeatureFlag.SUPPLIER_LEARNING, pilot)
    assert not is_rollout_enabled(settings, FeatureFlag.SUPPLIER_LEARNING, uuid4())


def test_flag_apagado_gana_siempre_incluso_para_tenant_allowlisted() -> None:
    pilot = uuid4()
    settings = _settings(supplier_learning_enabled=False, rollout_tenant_allowlist=[pilot])

    assert not is_rollout_enabled(settings, FeatureFlag.SUPPLIER_LEARNING, pilot)


@pytest.mark.parametrize("flag", tuple(FeatureFlag))
def test_cualquier_flag_se_puede_apagar_para_el_tenant_piloto(flag: FeatureFlag) -> None:
    """El rollback funcional de cualquier capacidad no depende de qué flag se haya elegido."""
    pilot = uuid4()
    settings = _settings(rollout_tenant_allowlist=[pilot], **{flag.value: False})

    assert not is_rollout_enabled(settings, flag, pilot)


def test_flags_evaluados_no_exponen_allowlist_y_respetan_el_tenant() -> None:
    pilot = uuid4()
    settings = _settings(rollout_tenant_allowlist=[pilot], draft_autosave_enabled=False)

    flags = evaluated_feature_flags(settings, pilot)

    assert flags[FeatureFlag.SUPPLIER_LEARNING.value] is True
    assert flags[FeatureFlag.DRAFT_AUTOSAVE.value] is False
    assert "rollout_tenant_allowlist" not in flags


def test_identidad_de_plataforma_no_recibe_flags_de_tenant() -> None:
    assert evaluated_feature_flags(_settings(), None) == {}

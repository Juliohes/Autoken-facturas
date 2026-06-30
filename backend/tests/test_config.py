"""Tests de la configuración de la aplicación (BP-5: log_level fail-loud)."""

import pytest
from pydantic import ValidationError

from shared.config import LogLevel, Settings


@pytest.mark.parametrize("nivel_invalido", ["warn", "verbose", "trace", "", "123"])
def test_log_level_invalido_falla_al_arrancar(nivel_invalido: str) -> None:
    """BP-5 (C1): un nivel de log inexistente lanza error de validación, no se traga."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(log_level=nivel_invalido)  # type: ignore[arg-type]
    assert "log_level" in str(exc_info.value)


@pytest.mark.parametrize("entrada", ["warning", "WARNING", "Warning"])
def test_log_level_valido_es_tolerante_a_la_caja(entrada: str) -> None:
    """BP-5 (C2): un nivel válido se acepta en cualquier caja y se normaliza."""
    settings = Settings(log_level=entrada)  # type: ignore[arg-type]
    assert settings.log_level is LogLevel.WARNING


def test_log_level_por_defecto_es_info() -> None:
    """El default sigue siendo INFO (no rompe el .env actual)."""
    assert Settings().log_level is LogLevel.INFO

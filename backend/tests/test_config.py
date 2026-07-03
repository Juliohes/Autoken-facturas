"""Tests de la configuración de la aplicación (BP-5: log_level fail-loud)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.config import LogLevel, Settings


def test_env_file_se_resuelve_a_la_raiz_del_monorepo() -> None:
    """El `.env` se ancla a la raíz del monorepo, no relativo al cwd.

    Regresión: arrancar el backend desde `backend/` (scripts, uvicorn) debe seguir leyendo el
    `.env` de la raíz. Antes se cargaba `env_file=".env"` relativo al cwd y no se encontraba la
    `MISTRAL_API_KEY`, aunque estuviera puesta.
    """
    env_file = Path(Settings.model_config["env_file"])  # type: ignore[arg-type]
    assert env_file.is_absolute()
    assert env_file.name == ".env"
    # La raíz es la carpeta que contiene `.env.example` (marcador estable del repo).
    assert (env_file.parent / ".env.example").is_file()


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

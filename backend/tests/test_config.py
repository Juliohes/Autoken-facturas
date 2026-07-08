"""Tests de la configuración de la aplicación (BP-5: log_level fail-loud)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from shared.config import AppEnv, LogLevel, Settings


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


@pytest.mark.parametrize(
    "secreto_inseguro",
    [
        "dev-insecure-jwt-secret-change-me",  # el default de dev: predecible, prohibido en prod
        "corto",  # menos de 32 bytes: firma HS256 débil
        "x" * 31,  # justo por debajo del mínimo de 32 bytes
    ],
)
def test_jwt_secret_inseguro_en_produccion_falla_al_arrancar(secreto_inseguro: str) -> None:
    """Un `jwt_secret` débil en producción hace fallar el arranque (fail-loud), no un warning."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(app_env=AppEnv.PRODUCTION, jwt_secret=secreto_inseguro)
    assert "JWT_SECRET" in str(exc_info.value)


def test_jwt_secret_fuerte_en_produccion_no_falla() -> None:
    """Con un secreto fuerte (>= 32 bytes y distinto del default), producción arranca sin error."""
    settings = Settings(app_env=AppEnv.PRODUCTION, jwt_secret="x" * 48)
    assert settings.is_production
    assert settings.jwt_secret == "x" * 48


@pytest.mark.parametrize("entorno", [AppEnv.DEVELOPMENT, AppEnv.STAGING])
def test_jwt_secret_default_es_aceptable_fuera_de_produccion(entorno: AppEnv) -> None:
    """En development/staging el default de dev no rompe (los tests y el arranque local lo usan)."""
    settings = Settings(app_env=entorno)
    assert settings.app_env is entorno

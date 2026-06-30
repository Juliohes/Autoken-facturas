"""Configuración de la aplicación vía pydantic-settings.

Lee variables de entorno (y un fichero .env en desarrollo). Nunca contiene
valores reales de secretos: el .env vive fuera del repo (ver .env.example).
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    """Entornos de ejecución soportados."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Niveles de log válidos (los de la librería estándar).

    Conjunto cerrado: cualquier otro valor en la configuración es un error que debe fallar al
    arrancar (fail-loud), no degradarse a INFO en silencio (BP-5).
    """

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Settings(BaseSettings):
    """Ajustes de la aplicación. Los campos se sobreescriben por env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Autoken Facturas v2"
    app_version: str = "0.1.0"
    app_env: AppEnv = AppEnv.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO
    api_prefix: str = "/api/v1"

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_log_level(cls, value: object) -> object:
        """Acepta el nivel en cualquier caja (INFO/info); la validez la decide `LogLevel`.

        No "arregla" valores inválidos: solo unifica la caja. Un nivel inexistente seguirá
        siendo un error de validación (fail-loud), en vez de tragarse y caer a INFO (BP-5).
        """
        return value.lower() if isinstance(value, str) else value

    # Base de datos (asyncpg). En desarrollo se puede dejar por defecto;
    # en staging/producción se inyecta por env var. No se conecta en 0.4.
    database_url: str = "postgresql+asyncpg://autoken_app:autoken@postgres:5432/autoken"

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada) para inyección de dependencias."""
    return Settings()

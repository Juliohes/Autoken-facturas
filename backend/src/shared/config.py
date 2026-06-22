"""Configuración de la aplicación vía pydantic-settings.

Lee variables de entorno (y un fichero .env en desarrollo). Nunca contiene
valores reales de secretos: el .env vive fuera del repo (ver .env.example).
"""

from decimal import Decimal
from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    """Entornos de ejecución soportados."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


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
    log_level: str = "info"
    api_prefix: str = "/api/v1"

    # Base de datos (asyncpg). En desarrollo se puede dejar por defecto;
    # en staging/producción se inyecta por env var. No se conecta en 0.4.
    database_url: str = "postgresql+asyncpg://autoken_app:autoken@postgres:5432/autoken"

    # OCR — Azure OpenAI (visión). Lo consume el adaptador del bench (tarea 1.2) y, más
    # adelante, el pipeline de extracción. Vacío por defecto: sin credenciales el motor no se
    # instancia (el bench lo omite). El despliegue debe ser Data Zone Standard / EU, NUNCA
    # Global (regla de residencia de datos, plan §3 + ADR-0007).
    azure_openai_endpoint: str = ""
    azure_openai_key: str = ""
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment: str = ""
    # Precios en EUR por 1.000 tokens (entrada/salida) para calcular el coste real del bench.
    # 0 = desconocido; se fija con la tarifa vigente del despliegue antes de comparar costes.
    azure_openai_eur_per_1k_input: Decimal = Decimal(0)
    azure_openai_eur_per_1k_output: Decimal = Decimal(0)

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada) para inyección de dependencias."""
    return Settings()

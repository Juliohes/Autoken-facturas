"""Configuración de la aplicación vía pydantic-settings.

Lee variables de entorno (y un fichero .env en desarrollo). Nunca contiene
valores reales de secretos: el .env vive fuera del repo (ver .env.example).
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_project_root() -> Path:
    """Raíz del monorepo: la carpeta que contiene `.env.example` (marcador estable del repo).

    Ancla el `.env` a una ruta absoluta para que la configuración funcione con independencia del
    directorio desde el que se arranque el proceso (uvicorn o scripts lanzados desde `backend/`).
    En contenedor no se copia `.env.example` y las vars llegan por entorno: el fallback a cwd es
    inocuo porque pydantic prioriza las variables de entorno sobre el fichero.
    """
    for parent in Path(__file__).resolve().parents:
        if (parent / ".env.example").is_file():
            return parent
    return Path.cwd()


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
        env_file=_find_project_root() / ".env",
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

    # OCR — Mistral OCR 4 (cabeza de serie del bench, Fase 1). La API key es un secreto y solo
    # vive en el `.env`/GitHub Secrets; el modelo y el timeout son configuración no secreta.
    mistral_api_key: str | None = None
    mistral_ocr_model: str = "mistral-ocr-4-0"
    mistral_ocr_timeout: int = 60

    # OCR — Azure Document Intelligence (candidato del bench). Endpoint y clave son secretos; el
    # modelo (`prebuilt-layout` da markdown con tablas) es configuración no secreta.
    azure_docintel_endpoint: str | None = None
    azure_docintel_key: str | None = None
    azure_docintel_model: str = "prebuilt-layout"

    # OCR — Google Gemini vía Vertex AI (candidatos del bench: Flash y Pro). El proyecto y la ruta
    # al JSON de la service account son secretos; la región y los ids de modelo no lo son. Los
    # nombres de campo mapean a las env vars estándar de Vertex (GOOGLE_CLOUD_*, GOOGLE_APP_*).
    google_cloud_project: str | None = None
    google_cloud_location: str = "europe-west4"
    google_application_credentials: str | None = None
    # Gemini 3 aún no está en europe-west4: se accede por el endpoint `global` (decisión de Julio,
    # 2026-07-04). Región propia para no atar el resto de usos Vertex a global. Ids verificados
    # contra `models.list()` de Vertex; `gemini-3-pro` pelado no existe, el Pro actual es 3.1.
    gemini_location: str = "global"
    gemini_flash_model: str = "gemini-3-flash-preview"
    gemini_pro_model: str = "gemini-3.1-pro-preview"

    # OCR — Azure OpenAI (gpt-5.1, chat-visión). Candidato del bench. Endpoint, clave y despliegue
    # son secretos; el despliegue debe ser Data Zone Standard / EU (nunca Global), por RGPD.
    azure_openai_endpoint: str | None = None
    azure_openai_key: str | None = None
    azure_openai_deployment: str | None = None
    azure_openai_api_version: str = "2024-12-01-preview"

    # OCR — Claude vía Vertex AI (candidato del bench). Reusa proyecto/credenciales de Google
    # (mismos que Gemini). Ids/regiones verificados contra el listado de publisher models de Vertex
    # (2026-07-04): en `europe-west1` (UE, RGPD) está `claude-sonnet-4-5`; los más nuevos
    # (sonnet-4-6, opus-4-8, sonnet-5) solo en `global`. Ajustables en el `.env`.
    claude_location: str = "europe-west1"
    claude_model: str = "claude-sonnet-4-5@20250929"

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada) para inyección de dependencias."""
    return Settings()

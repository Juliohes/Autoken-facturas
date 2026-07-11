"""Configuración de la aplicación vía pydantic-settings.

Lee variables de entorno (y un fichero .env en desarrollo). Nunca contiene
valores reales de secretos: el .env vive fuera del repo (ver .env.example).
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Valor por defecto del secreto JWT: SOLO para desarrollo/test. En producción se rechaza al arrancar
# (ver `_reject_insecure_jwt_secret_in_production`). En constante para que el guard lo compare sin
# duplicar el literal.
_DEV_JWT_SECRET = "dev-insecure-jwt-secret-change-me"  # noqa: S105  (solo dev/test)
# Longitud mínima del secreto en producción: 32 bytes de entropía para HS256 (una clave más corta
# debilita la firma y facilita falsificar sesiones).
_MIN_JWT_SECRET_BYTES = 32


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

    @model_validator(mode="after")
    def _reject_insecure_jwt_secret_in_production(self) -> Self:
        """En producción, un `jwt_secret` débil hace fallar el arranque (fail-loud), no un warning.

        Un secreto predecible (el default de dev) o demasiado corto permitiría falsificar access
        tokens y, con ellos, sesiones de cualquier usuario. En development/staging no se aplica: los
        tests y el arranque local usan el default a propósito.
        """
        if self.app_env is AppEnv.PRODUCTION:
            if self.jwt_secret == _DEV_JWT_SECRET:
                raise ValueError(
                    "JWT_SECRET no puede ser el valor por defecto de desarrollo en producción: "
                    "inyecta un secreto real por la variable de entorno JWT_SECRET."
                )
            if len(self.jwt_secret.encode("utf-8")) < _MIN_JWT_SECRET_BYTES:
                raise ValueError(
                    f"JWT_SECRET debe tener al menos {_MIN_JWT_SECRET_BYTES} bytes en producción "
                    "para firmar de forma segura los access token (HS256)."
                )
        return self

    # Base de datos (asyncpg). En desarrollo se puede dejar por defecto;
    # en staging/producción se inyecta por env var. No se conecta en 0.4.
    database_url: str = "postgresql+asyncpg://autoken_app:autoken@postgres:5432/autoken"

    # Dominio base para extraer el subdominio->tenant (S1.2). `localhost` se acepta además en
    # desarrollo (p. ej. `ilex.localhost`). Los subdominios de plataforma no resuelven a tenant.
    base_domain: str = "autoken.es"

    # Caché de resolución subdominio->tenant (#52, ADR-0014). Blinda la BD frente al DoS y la
    # enumeración pre-auth cacheando el veredicto NEGATIVO (slug que no resuelve) con TTL corto y
    # cota LRU. Los positivos no se cachean (revocación instantánea de tenants suspendidos). TTL
    # bajo a propósito: acota la staleness de un tenant recién creado a unos segundos.
    subdomain_cache_ttl_seconds: int = 30
    subdomain_cache_max_size: int = 1024

    # --- Autenticación S1.3 (identity) ---------------------------------------------------------
    # Redis: rate-limit de login, rotación del refresh y tokens de activación. La URL no es secreta
    # (no lleva credenciales en dev/CI); en producción puede incluir password vía env var.
    redis_url: str = "redis://redis:6379/0"

    # `jwt_secret` firma los access token (HS256). Es SECRETO: en staging/producción llega por env
    # var `JWT_SECRET` (§9.1); el valor por defecto es solo para desarrollo/test y NUNCA se usa en
    # producción (una firma predecible permitiría falsificar sesiones).
    jwt_secret: str = _DEV_JWT_SECRET
    jwt_access_ttl: int = 15 * 60  # access token de vida corta (15 min), en segundos
    jwt_refresh_ttl: int = 14 * 24 * 60 * 60  # refresh de vida larga (14 días), en segundos

    # Política de contraseñas y límite de fuerza bruta (por (IP+email) y un tope más grueso por IP).
    password_min_length: int = 12
    password_max_length: int = 128  # acota el coste de hashing (DoS) ante contraseñas larguísimas
    login_max_attempts: int = 5  # fallos por (IP+email) en la ventana antes del 429
    login_window_seconds: int = 15 * 60  # ventana del rate-limit (15 min)
    login_ip_max_attempts: int = 20  # tope más grueso por IP (credential spraying)

    activation_ttl: int = 72 * 60 * 60  # token de activación de un solo uso (72 h), en segundos

    # --- Registro con aprobación S1.4 (identity + notifications) --------------------------------
    # Anti-spam del registro público (`POST /register`): tope de altas por IP en una ventana
    # (reutiliza la infra de rate-limit en Redis de S1.3). Al superarlo, los siguientes reciben 429.
    register_max_per_ip: int = 20
    register_window_seconds: int = 60 * 60  # ventana del rate-limit de registro (1 h)

    # Notificaciones (aviso al `tenant_admin` de un registro pendiente). El envío real por SMTP está
    # diferido (spec S1.4 §6): SIN `smtp_host` se usa el grabador en memoria (RecordingNotifier);
    # cuando existan las credenciales de soporte@autoken.es se cablea el transporte SMTP. Secreto:
    # llega por env var en el VPS (§9.1), nunca en el repo.
    smtp_host: str | None = None

    # --- Importación de empresas S1.5 (companies) ----------------------------------------------
    # Guardarraíles anti-DoS por memoria del `POST /companies/import` (proceso compartido por todas
    # las asesorías): un `.xlsx` manipulado (zip-bomb) o gigantesco no debe tumbar el backend. Tope
    # de tamaño del fichero subido (se rechaza con 413 antes de parsear) y tope de filas de datos a
    # procesar (corta el parseo y marca el informe como truncado).
    companies_import_max_bytes: int = 5 * 1024 * 1024  # 5 MB
    companies_import_max_rows: int = 5_000

    # Proxies de confianza (Traefik/Caddy) desde los que se acepta `X-Forwarded-For` para derivar la
    # IP real del cliente en el rate-limit (C17/C22). Lista separada por comas de IPs exactas del
    # peer directo. VACÍO por defecto: nunca se confía en XFF, la IP es la del peer. En producción
    # se fija a la red del proxy con `--proxy-headers --forwarded-allow-ips=<misma lista>`.
    #
    # FOOT-GUN: `"*"` (opt-in, nunca el default) confía en el XFF más a la izquierda venga de
    # donde venga y DESACTIVA la protección anti-spoofing del rate-limit por IP: un atacante rota
    # la cabecera en cada intento y no llega al tope. Úsalo solo si un proxy de confianza REESCRIBE
    # siempre `X-Forwarded-For` descartando el que mande el cliente; con una lista de IPs concretas
    # se toma el primer salto no confiable desde la derecha, que sí es fiable.
    trusted_proxies: str = ""

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
    # (mismos que Gemini). CORRECCIÓN 2026-07-05: contra el proyecto real, `europe-west1` y
    # `europe-west4` dan 404 (no hay publisher model de Anthropic ahí); Claude solo se sirve por el
    # endpoint `global`, donde el id existe pero el proyecto tiene **cuota 0**
    # (`global_online_prediction_requests_per_base_model` → 429). Hasta que Julio pida aumento de
    # cuota para los base models de Anthropic en la consola de GCP, Claude no puede entrar al bench.
    # Ajustables en el `.env`. Ver §11.10 del plan.
    claude_location: str = "global"
    claude_model: str = "claude-sonnet-4-5@20250929"

    # --- Intake seguro de ficheros S2.1 (invoice_intake) ---------------------------------------
    # Object storage MinIO (bucket por tenant, ADR-0015). Endpoint/credenciales son secretos en
    # producción (llegan por env var, §9.1); los valores por defecto son SOLO para desarrollo/CI,
    # donde se levanta un MinIO local con las credenciales estándar `minioadmin`. `minio_secure`
    # activa TLS (true en producción tras el proxy).
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"  # noqa: S105  (solo default de dev/CI)
    minio_secure: bool = False

    # Tamaño máximo del fichero de intake (se rechaza con 413 antes de procesarlo). No es una regla
    # de dominio: es un guardarraíl anti-DoS configurable. Por defecto 15 MiB.
    max_upload_bytes: int = 15 * 1024 * 1024

    # Antivirus (fail-closed, ADR-0015). `virus_scanner_backend` fuerza el backend (`signature` o
    # `clamd`); sin fijar, se usa el scanner de firma en dev/CI (detecta EICAR en proceso, sin red)
    # y ClamAV real (clamd) en producción. Host/puerto del daemon clamd (solo aplican al backend
    # `clamd`).
    virus_scanner_backend: str | None = None
    clamav_host: str = "clamav"
    clamav_port: int = 3310

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def trusted_proxy_set(self) -> frozenset[str]:
        """`trusted_proxies` como conjunto de IPs (o `{'*'}`); vacío si no hay ninguno."""
        return frozenset(item.strip() for item in self.trusted_proxies.split(",") if item.strip())


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada) para inyección de dependencias."""
    return Settings()

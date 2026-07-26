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

# Mismo criterio que `_DEV_JWT_SECRET`, para la clave maestra de cifrado en reposo (S5.2).
_DEV_ENCRYPTION_MASTER_KEY = "dev-insecure-encryption-master-key-change-me"  # noqa: S105
_MIN_ENCRYPTION_MASTER_KEY_BYTES = 32

# Mismo criterio, para la clave de cifrado de los backups completos (S5.3). Secreto DISTINTO del de
# arriba a propósito (ver `shared/backup_encryption.py`): protegen modelos de amenaza distintos.
_DEV_BACKUP_ENCRYPTION_KEY = "dev-insecure-backup-encryption-key-change-me"  # noqa: S105
_MIN_BACKUP_ENCRYPTION_KEY_BYTES = 32


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

    @model_validator(mode="after")
    def _reject_insecure_encryption_master_key_in_production(self) -> Self:
        """En producción, una `db_encryption_master_key` débil hace fallar el arranque (fail-loud,
        S5.2 spec §5): con una clave predecible, el cifrado en reposo de CIF/nombre no protege nada
        de verdad. Mismo criterio que `jwt_secret`."""
        if self.app_env is AppEnv.PRODUCTION:
            if self.db_encryption_master_key == _DEV_ENCRYPTION_MASTER_KEY:
                raise ValueError(
                    "DB_ENCRYPTION_MASTER_KEY no puede ser el valor por defecto de desarrollo en "
                    "producción: inyecta una clave real por la variable de entorno "
                    "DB_ENCRYPTION_MASTER_KEY."
                )
            if (
                len(self.db_encryption_master_key.encode("utf-8"))
                < _MIN_ENCRYPTION_MASTER_KEY_BYTES
            ):
                raise ValueError(
                    "DB_ENCRYPTION_MASTER_KEY debe tener al menos "
                    f"{_MIN_ENCRYPTION_MASTER_KEY_BYTES} bytes en producción para derivar claves "
                    "de cifrado por tenant con suficiente entropía."
                )
        return self

    # Base de datos (asyncpg). En desarrollo se puede dejar por defecto;
    # en staging/producción se inyecta por env var. No se conecta en 0.4.
    database_url: str = "postgresql+asyncpg://autoken_app:autoken@postgres:5432/autoken"

    # Tamaño del pool de conexiones de SQLAlchemy (S5.5, hallazgo real de la prueba de carga): sin
    # fijarlo, el default de SQLAlchemy (`pool_size=5, max_overflow=10`, 15 conexiones simultáneas
    # como máximo) se agota con una carga de subida de facturas moderadamente concurrente, dejando
    # peticiones en cola hasta `pool_timeout` (30s) y fallando después — exactamente lo que se
    # reprodujo con 50 subidas a la vez (43/50 fallos, p95 ~32s) antes de subir estos valores.
    # Configurable, no hardcodeado en `shared/db.py`: en un despliegue con varias réplicas de la
    # app, el total de conexiones a Postgres es la suma de todas — ajustar aquí, no en el código.
    db_pool_size: int = 20
    db_max_overflow: int = 20

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

    # Cifrado en reposo por tenant (S5.2, `shared/encryption.py`): clave maestra única de la que se
    # DERIVAN (nunca se guardan) una clave de cifrado y una de índice ciego distintas por tenant.
    # Mismo criterio que `jwt_secret`: SECRETO, por env var `DB_ENCRYPTION_MASTER_KEY` en
    # staging/producción, nunca en el repo.
    db_encryption_master_key: str = _DEV_ENCRYPTION_MASTER_KEY

    # Cifrado de los backups completos de la base de datos (S5.3, `jobs/backup.py`). Secreto
    # DISTINTO de `db_encryption_master_key` a propósito (ver `shared/backup_encryption.py`): mismo
    # criterio de secreto por env var (`BACKUP_ENCRYPTION_KEY`), nunca en el repo. Su fortaleza NO
    # se valida aquí (a diferencia de `jwt_secret`/`db_encryption_master_key`): solo lo usan los
    # scripts de backup, nunca la API/worker — ver `require_strong_backup_encryption_key`.
    backup_encryption_key: str = _DEV_BACKUP_ENCRYPTION_KEY

    # Política de contraseñas y límite de fuerza bruta (por (IP+email) y un tope más grueso por IP).
    password_min_length: int = 12
    password_max_length: int = 128  # acota el coste de hashing (DoS) ante contraseñas larguísimas
    login_max_attempts: int = 5  # fallos por (IP+email) en la ventana antes del 429
    login_window_seconds: int = 15 * 60  # ventana del rate-limit (15 min)
    login_ip_max_attempts: int = 20  # tope más grueso por IP (credential spraying)

    activation_ttl: int = 72 * 60 * 60  # token de activación de un solo uso (72 h), en segundos

    # Rate-limit de endpoints sensibles sin protección previa (S5.1 C3-C8): mismo patrón de ventana
    # deslizante en Redis que el login. `activation_confirm_*` es por TOKEN (fuerza bruta del TOTP
    # de 6 dígitos al confirmar la activación); `refresh_*` es por IP (abuso de rotación).
    activation_confirm_max_attempts: int = 5
    activation_confirm_window_seconds: int = 15 * 60
    refresh_max_attempts: int = 20
    refresh_window_seconds: int = 15 * 60

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

    # Cota del tamaño total del CUERPO de la petición (issue #66): un middleware la rechaza con 413
    # por `Content-Length` ANTES de que Starlette/python-multipart vuelque el cuerpo a disco
    # (defensa anti-DoS de disco). Debe superar `max_upload_bytes` para dejar hueco al envoltorio
    # multipart (boundaries + el campo `company_id`). Por defecto 16 MiB. En prod, el proxy inverso
    # debe poner además su propia cota (defensa en profundidad).
    max_request_body_bytes: int = 16 * 1024 * 1024

    # --- Worker OCR S2.3 (jobs, arq) -----------------------------------------------------------
    # Cola de arq en la que la API encola `run_ocr` tras una subida aceptada y de la que el worker
    # consume. No es secreto; se comparte el mismo Redis que el resto de la app.
    ocr_queue_name: str = "autoken:queue:ocr"

    # Antivirus (fail-closed, ADR-0015). `virus_scanner_backend` fuerza el backend (`signature` o
    # `clamd`); sin fijar, se usa el scanner de firma en dev/CI (detecta EICAR en proceso, sin red)
    # y ClamAV real (clamd) en producción. Host/puerto del daemon clamd (solo aplican al backend
    # `clamd`).
    virus_scanner_backend: str | None = None
    clamav_host: str = "clamav"
    clamav_port: int = 3310

    # --- Verificación del CIF de contraparte S2.8 (counterparty, ADR-0011) ----------------------
    # Fuentes externas (L3) tras la interfaz `CifResolver`. En CI los resolvers van doblados; estos
    # ajustes solo se usan al construir los clientes REALES (staging). Endpoints y timeouts no son
    # secretos; el certificado de AEAT y su contraseña SÍ (llegan por env var en el VPS, §9.1).
    #
    # AEAT censal (VNifV2, SOAP mutual-TLS): fuente autoritativa del par CIF+nombre. El certificado
    # electrónico de Julio se monta como fichero PEM (cert+clave) en `secrets/` (gitignored); su
    # contraseña protege la clave privada. El endpoint (preproducción vs producción) se confirma en
    # staging. Sin certificado/endpoint el resolver no se construye (fuente no disponible).
    aeat_endpoint: str | None = None
    aeat_cert_path: str | None = None
    aeat_cert_password: str | None = None
    aeat_timeout: int = 10  # segundos

    # VIES (`checkVatApprox`, SOAP público de la Comisión Europea): determinante solo intra-UE.
    vies_endpoint: str = "https://ec.europa.eu/taxation_customs/vies/services/checkVatService.wsdl"
    vies_timeout: int = (
        10  # segundos (el VIES cae a menudo: timeout corto -> unverified, no bloqueo)
    )

    # BORME (OpenMercantil/LibreBOR, HTTP público): enriquece CIF->razón social de sociedades.
    borme_base_url: str | None = None
    borme_timeout: int = 10  # segundos

    # TTL de la caché global de resoluciones (`cif_lookups`, L4). Los datos de registros públicos
    # cambian rara vez; 30 días equilibra frescura y ahorro de cuota/latencia.
    cif_cache_ttl_seconds: int = 30 * 24 * 60 * 60

    # --- Observabilidad S5.6 (captura de errores + métricas) ------------------------------------
    # Sentry se activa SOLO si hay DSN (`shared.error_tracking.init_sentry`); sin él, no hace nada.
    sentry_dsn: str | None = None

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def trusted_proxy_set(self) -> frozenset[str]:
        """`trusted_proxies` como conjunto de IPs (o `{'*'}`); vacío si no hay ninguno."""
        return frozenset(item.strip() for item in self.trusted_proxies.split(",") if item.strip())


def require_strong_backup_encryption_key(settings: Settings) -> None:
    """Comprueba que `backup_encryption_key` es apta para cifrar un backup real (S5.3 spec §4).

    A propósito, NO es un `model_validator` de `Settings` (a diferencia de `jwt_secret`/
    `db_encryption_master_key`, que SÍ lo son): esos dos los usa la API/worker en cada petición, así
    que validarlos al construir `Settings` tiene sentido. `backup_encryption_key` en cambio solo lo
    usan `scripts/backup_database.py`/`scripts/restore_drill.py` — si fuera un `model_validator`
    global, la API y el worker en producción se negarían a arrancar sin ese secreto, aunque nunca lo
    usan, obligando a inyectarlo también en su entorno (compartido, `env_file` de
    `docker-compose.yml`) y deshaciendo el aislamiento de secretos que es la razón de ser de
    ADR-0019 (hallazgo de auditoría). Se llama explícitamente solo desde los dos scripts de backup.
    """
    if settings.backup_encryption_key == _DEV_BACKUP_ENCRYPTION_KEY:
        raise ValueError(
            "BACKUP_ENCRYPTION_KEY no puede ser el valor por defecto de desarrollo: inyecta una "
            "clave real por la variable de entorno BACKUP_ENCRYPTION_KEY."
        )
    if len(settings.backup_encryption_key.encode("utf-8")) < _MIN_BACKUP_ENCRYPTION_KEY_BYTES:
        raise ValueError(
            f"BACKUP_ENCRYPTION_KEY debe tener al menos {_MIN_BACKUP_ENCRYPTION_KEY_BYTES} bytes "
            "para cifrar los backups completos con suficiente entropía."
        )


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración (cacheada) para inyección de dependencias."""
    return Settings()

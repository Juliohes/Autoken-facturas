# Backend Autoken Facturas v2 — imagen de la API FastAPI
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencias del sistema mínimas (curl para el healthcheck del contenedor)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar dependencias primero (mejor caché de capas)
COPY pyproject.toml ./
COPY src ./src
RUN pip install .
# Worker OCR S2.3 (arq) horneado en la imagen (la usa el servicio `worker` de docker-compose). Se
# instala con `--no-deps` para NO degradar redis: arq declara `redis<6` pero opera con el redis 8 de
# la app (compatibilidad verificada por el smoke test tests/test_ocr_worker_wiring.py); sus otras deps
# (click) ya vienen con uvicorn. Ver el extra `worker` en pyproject.toml.
RUN pip install --no-deps "arq>=0.26"

# Usuario no-root
RUN useradd --create-home --uid 10001 appuser
COPY alembic.ini ./
COPY migrations ./migrations
COPY scripts/create_account.py ./scripts/
RUN chown -R appuser:appuser /app

# --- Imagen "ops": herramientas de mantenimiento (backup/restore, S5.3) -------------------------
# Estadio SEPARADO de la imagen "api" de más abajo (la que sirve tráfico HTTP público/worker OCR):
# nunca lleva `postgresql-client` ni corre con `BACKUP_DATABASE_ADMIN_DSN`/`BACKUP_ENCRYPTION_KEY`
# en su entorno — un RCE contra el contenedor expuesto a internet no debe heredar de regalo la
# herramienta ni la superficie extra de `pg_dump`/`pg_restore` (hallazgo de auditoría: instalarlo en
# la imagen de la API amplía su superficie sin necesidad). NO es el target por defecto de
# `docker build .` (que resuelve al último `FROM`, `api`): se construye explícitamente con
# `docker build --target ops`, ejecutado desde cron/un contenedor puntual, nunca desde `api`/`worker`.
FROM base AS ops
# `postgresql-client` SIN versión (el paquete Debian de la imagen base) resuelve a la versión mayor
# más reciente (17 hoy) — probado en real contra el Postgres 16 del proyecto y falla: `pg_dump`/
# `pg_restore` v17 emiten `SET transaction_timeout = 0` en el volcado, un parámetro que NO existe en
# el servidor v16 ("unrecognized configuration parameter"), tumbando cualquier restore real.
# Se instala la v16 exacta desde el repositorio oficial de PostgreSQL (PGDG), no el de Debian.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -sSf -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && rm -rf /var/lib/apt/lists/*
COPY scripts/backup_database.py scripts/restore_drill.py ./scripts/
USER appuser
ENTRYPOINT ["python"]

# --- Imagen "api": la que sirve tráfico HTTP y el worker OCR (target por defecto) ---------------
FROM base AS api
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

# `--proxy-headers` habilita el uso de `X-Forwarded-*` detrás del proxy inverso (Traefik/Caddy).
# uvicorn solo reescribe la IP del cliente si el peer TCP está en `--forwarded-allow-ips`, que toma
# del entorno `FORWARDED_ALLOW_IPS` (por defecto 127.0.0.1). Debe alinearse con `TRUSTED_PROXIES` de
# la app (rate-limit por IP real, B1/C22). Ver docker-compose.yml e infra de producción.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

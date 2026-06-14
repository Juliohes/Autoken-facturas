# Backend — Autoken Facturas v2

API FastAPI (Python 3.12, async). Monolito modular (Screaming Architecture): cada
dominio en su paquete bajo `src/` (tenancy, security, identity, companies,
invoice_intake, ocr, platform_admin, reporting, ...).

## Estado (0.4 — esqueleto)
- App FastAPI con application factory (`src/main.py`).
- Healthcheck: `GET /api/v1/health`.
- Logging estructurado JSON (structlog) con correlation id por petición.
- Configuración con pydantic-settings (`src/shared/config.py`).
- Alembic inicializado (async) — la metadata de modelos se enlaza en S1.1.

## Desarrollo local

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"

# Calidad
ruff check src tests
ruff format --check src tests
mypy src
pytest -q

# Arrancar la API (recarga en caliente)
uvicorn main:app --reload --app-dir src
# Healthcheck: http://localhost:8000/api/v1/health  ·  Docs: /docs
```

## Docker

```bash
docker build -t autoken/api:dev .
# O con la pila completa (api + postgres + redis):
docker compose -f ../infrastructure/docker-compose.yml up --build
```

## Migraciones
Ver `migrations/README.md`. La URL de BD se toma de `DATABASE_URL` (nunca de `alembic.ini`).

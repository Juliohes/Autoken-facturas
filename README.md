# Autoken Facturas v2 (Setex v2)

Plataforma **SaaS multi-asesoría white-label** de digitalización de facturas con OCR/IA.
Backend Python/FastAPI + Frontend React PWA, multi-tenant con aislamiento total por asesoría
(PostgreSQL Row-Level Security de dos niveles + buckets separados + cifrado por tenant).

> **Fuente de verdad del proyecto**: [`PLAN_MAESTRO_AUTOKEN_FACTURAS_V2_v1.2.md`](./PLAN_MAESTRO_AUTOKEN_FACTURAS_V2_v1.2.md).
> Resumen operativo para retomar contexto: [`CLAUDE.md`](./CLAUDE.md).

## Estructura del monorepo

```
backend/          # Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, PostgreSQL 16, Redis, arq, MinIO
  src/            # Monolito modular (Screaming Architecture): tenancy, security, identity, companies,
                  # invoice_intake, ocr, platform_admin, reporting, notifications, jobs, shared, ...
  tests/          # Unitarios + integración + suite anti-cruce de tenants (gate de CI)
frontend/         # React 18 + Vite + TypeScript, TanStack Query, Tailwind, shadcn/ui, PWA
infrastructure/   # Docker Compose (caddy, api, worker, postgres, redis, minio, clamav), despliegue
docs/             # Arquitectura, ADRs (docs/adr/), runbooks (docs/runbooks/), evaluación OCR (docs/ocr-eval/)
```

## Quickstart (en construcción)

El esqueleto ejecutable llega en las tareas **0.4** (backend) y **0.5** (frontend) de la Fase 0.
Hasta entonces este repo contiene el scaffolding del monorepo, la configuración de calidad y CI.

```bash
# (Pendiente 0.4) Levantar backend en Docker
# docker compose -f infrastructure/docker-compose.yml up api
# Healthcheck: GET /api/v1/health
```

## Convenciones (resumen — ver CLAUDE.md y plan §2)

- **Ramas**: `main` (prod) · `develop` (integración) · `feature/<ID>-<slug>` (una por tarea del plan).
- **Commits**: Conventional Commits `tipo(ámbito): descripción` referenciando el ID de tarea.
- **Idioma**: código en inglés; comentarios de dominio, ADRs y docs en español.
- **Secretos**: nunca en el repo. Ver [`.env.example`](./.env.example) y el mapa de secretos del plan (§9.1).

## Seguridad

- Aislamiento multi-tenant verificado por suite anti-cruce (gate de CI bloqueante).
- Anti-alucinación OCR: campo no legible = `null` + aviso; nunca un valor inventado.
- `.env` ignorado desde el primer commit; `gitleaks` como pre-commit y en CI.

## Licencia

Privado — todos los derechos reservados.

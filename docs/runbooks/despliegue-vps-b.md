# Runbook — Despliegue real en VPS B (`2.24.8.109`)

> Primer despliegue real del stack completo, 2026-07-27. Sirve `panel-staging.autoken.es` detrás
> del Traefik ya existente en `/opt/traefik` (Let's Encrypt real, red Docker `proxy`). Ver
> `infrastructure/docker-compose.yml` + `infrastructure/docker-compose.prod.yml`.

## Qué hay desplegado hoy

- `api`/`worker`/`postgres`/`redis`/`minio`/`clamav` + observabilidad (`prometheus`/`alertmanager`/
  `grafana`/`node-exporter`) — proyecto Docker Compose `infrastructure`.
- `panel-staging.autoken.es` → TLS real (Let's Encrypt), enrutado por el Traefik que ya sirve
  `autoken.es` (proyecto Docker Compose separado, `/opt/traefik`, **no tocar**).
- Todos los secretos reales viven en `/opt/app-facturas/.env` (permisos `600`, fuera de git).

## Levantar / relanzar el stack

Desde `infrastructure/`, siempre con `--env-file ../.env` y ambos ficheros de compose:

```bash
cd /opt/app-facturas/infrastructure
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Primera vez en una base de datos nueva (o tras borrar el volumen)

El superusuario admin (`POSTGRES_ADMIN_USER`/`POSTGRES_ADMIN_PASSWORD`) y el rol runtime
`autoken_app` son DISTINTOS a propósito (ver el commit que corrigió esto — antes `autoken_app` era
sin querer el propio superusuario del clúster, y la migración 0001 no llegaba a crear el rol
restringido de verdad). Tras levantar `postgres` y que esté sano:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml \
  --profile tools run --rm migrate            # aplica Alembic como admin

docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml \
  --profile tools run --rm provision-app-role  # concede LOGIN a autoken_app
```

Solo entonces `api`/`worker` arrancan correctamente (si no, el guard `assert_runtime_role_cannot_
bypass_rls`, ADR-0014, aborta el arranque — es la protección funcionando, no un bug).

## Acceder a Grafana/Prometheus/Alertmanager (solo por túnel SSH, nunca públicos)

Estos tres puertos están en `127.0.0.1` de la VPS a propósito (sin autenticación propia salvo
Grafana) — el acceso remoto es por túnel:

```bash
ssh -L 3001:127.0.0.1:3001 -L 9090:127.0.0.1:9090 -L 9093:127.0.0.1:9093 deploy@2.24.8.109
```

Luego, en tu propio navegador: `http://localhost:3001` (Grafana, usuario `admin`, contraseña en
`GRAFANA_ADMIN_PASSWORD` del `.env` real), `http://localhost:9090` (Prometheus),
`http://localhost:9093` (Alertmanager).

## Desplegar otro entorno/dominio con el mismo mecanismo

`docker-compose.prod.yml` usa `PUBLIC_HOST`/`PUBLIC_HOST_SLUG` (por defecto
`panel-staging.autoken.es`/`panel-staging`). Para otro dominio (p. ej. producción real, D.1),
sobreescribe esas dos variables en `.env` antes de `up` — el DNS de ese dominio debe apuntar ya a
esta VPS (HTTP-01: Let's Encrypt valida por HTTP antes de emitir).

## Pendiente (fuera de alcance de este despliegue)

- Backups reales (S5.3): el mecanismo ya está construido y probado (`docs/runbooks/backups-restore.md`)
  pero el cron + destino externo siguen sin conectar — pendiente de que Julio contrate el
  VPS/Storage de Hostinger para backups.
- Dominios propios de CLIENTE (que una gestoría use su propio dominio, no un subdominio nuestro):
  Traefik con HTTP-01 funciona bien para dominios conocidos de antemano (como este), pero un dominio
  arbitrario que un tenant añada en caliente necesita un mecanismo dinámico de routers/certificados
  (fuera de alcance de esta sesión) — tarea aparte.
- Credenciales reales de IA (Azure/Vertex/Mistral) para este staging: no se ha verificado si el
  `.env` ya las trae completas para el worker (`secrets/vertex-sa.json` es un placeholder `{}` por
  ahora) — no hacía falta para validar TLS/monitorización/backups, pero el worker no procesará OCR
  real hasta que se rellene de verdad.

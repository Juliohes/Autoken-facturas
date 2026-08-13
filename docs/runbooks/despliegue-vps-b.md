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

### Antivirus no disponible al subir una factura

La subida se bloquea intencionadamente si ClamAV no puede escanear el fichero: nunca se desactiva el
antivirus ni se acepta una foto sin analizar. Comprueba primero:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml ps clamav
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml exec clamav clamdcheck.sh
```

El healthcheck reinicia automáticamente el contenedor tras tres fallos consecutivos de `clamd`. Si
continúa fallando, revisa sus logs antes de reiniciarlo manualmente:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml logs --tail=200 clamav
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml restart clamav
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

### Migración 0033: cifrado del histórico experimental OCR

La migración `0033_encrypt_ocr_experiment_pii` cifra el CIF y nombre de contraparte almacenados en
experimentos anteriores. API y worker deben estar detenidos: una imagen antigua volvería a escribir
esos campos dentro del JSONB en claro.

1. `docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml stop api worker`
2. Ejecutar `docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml --profile tools run --rm migrate`.
3. Levantar solo las imágenes nuevas con `docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d api worker`.

`migrate` recibe explícitamente `DB_ENCRYPTION_MASTER_KEY`, sin montar el `.env` completo, para
derivar exactamente las mismas claves por tenant que usará la aplicación. La migración bloquea ambas
tablas durante el backfill; no reanudar una imagen anterior tras aplicarla.

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

- Dominios propios de CLIENTE (que una gestoría use su propio dominio, no un subdominio nuestro):
  Traefik con HTTP-01 funciona bien para dominios conocidos de antemano (como este), pero un dominio
  arbitrario que un tenant añada en caliente necesita un mecanismo dinámico de routers/certificados
  (fuera de alcance de esta sesión) — tarea aparte.
- Las 20 facturas reales de `entregas/facturas/` (recogidas en su día para el bench de OCR de Fase 1,
  README de `entregas/`) NO corresponden a ninguna de las 61 empresas reales de Setex ya cargadas en
  `setex` — comprobado abriendo varias: el "Cliente" de la factura (p. ej. "Estudio Inghervi, S.L.U.",
  "Ingenieros Consultores Global Energy S.L.") no aparece en el Excel de las 61. Decisión de Julio
  (2026-07-27): dejarlas fuera por ahora, no forzar una asignación de empresa que no sea real.
  Retomar solo si Julio decide crear esas empresas de verdad en `setex` (una por factura) o traer
  facturas ya vinculadas a las 61 existentes. La credencial real de Vertex/Gemini ya está conectada
  (ver más abajo) para cuando se retome.

## Tenants reales servidos por este despliegue (actualizado 2026-07-27)

- `panel-staging.autoken.es`: host de plataforma (login `platform_admin`), no un tenant.
- `ilex.autoken.es`: tenant **demo**, deliberadamente vacío (solo para probar el panel sin datos reales).
- `setex.autoken.es`: tenant **real** — empresas y facturas reales de Setex (la app v1 que este
  proyecto sustituye). Router Traefik `setex-api`/`setex-web` añadido con el mismo patrón
  `.service=` explícito que `ilex-api`/`ilex-web` (ver comentarios en `docker-compose.prod.yml`).
- Credenciales reales de IA para el worker: `secrets/vertex-sa.json` ya NO es el placeholder `{}` —
  se sustituyó por la credencial real del proyecto `autoken-ocr` (la misma que usó el bench de Fase
  1, `secrets/autoken-ocr-91836920aea8.json`), montada tal cual por el mismo volumen. `worker`
  recreado para recogerla.

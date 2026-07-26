# Runbook — Observabilidad (S5.6): Sentry + Prometheus + Grafana + Alertmanager

> Estado al 2026-07-26. Stack completo y versionado (código de aplicación + infraestructura como
> código), **pendiente de desplegarse de verdad contra la VPS B** — mismo patrón que el Caddy/TLS
> real de S4.6: se construye ahora, se verifica end-to-end en una sesión futura con acceso a esa
> infraestructura. Ver spec `docs/specs/S5.6-monitorizacion-y-alertas.md`.

## Qué hay ya construido

- **Sentry** (`backend/src/shared/error_tracking.py`): se activa solo si `SENTRY_DSN` está en el
  entorno; sin él, no hace nada (coste y riesgo cero). Julio aún no tiene cuenta.
- **Métricas** (`GET /api/v1/metrics`, `backend/src/shared/metrics.py`): peticiones HTTP por
  método/código de estado (deriva la tasa de 5xx) y salud de la cola OCR (`autoken_ocr_queue_depth`,
  `autoken_ocr_queue_oldest_pending_seconds`, vía `backend/src/jobs/monitoring.py`, API pública de
  arq — no reconstruye claves de Redis a mano).
- **Prometheus + reglas de alerta** (`infrastructure/prometheus/`): scrapea la API y node-exporter;
  reglas para caída de la API, tasa alta de 5xx, cola OCR atascada (>10 min) y disco bajo mínimo
  (<10%). Validadas con `promtool check config`/`check rules` reales (vía `docker run`).
- **Alertmanager** (`infrastructure/alertmanager/`): recibe las alertas; receptor `null` por
  defecto (no envía nada a ningún sitio) hasta que Julio decida el canal real.
- **Grafana** (`infrastructure/grafana/`): datasource + dashboard básico provisionados por código
  (peticiones por estado, tasa de 5xx, profundidad y antigüedad de la cola OCR).
- **docker-compose**: los 4 servicios nuevos (`prometheus`, `alertmanager`, `grafana`,
  `node-exporter`) añadidos a `infrastructure/docker-compose.yml`, validado con
  `docker compose config`.

## Qué falta para que sea real (pendiente de Julio / de una sesión con acceso a la VPS B)

1. **Cuenta de Sentry**: crearla y poner el DSN en el `.env` real del servidor (`SENTRY_DSN=...`).
2. **Desplegar el stack en la VPS B**: `docker compose up -d prometheus alertmanager grafana
   node-exporter` (o el `up -d` completo). Cambiar `GRAFANA_ADMIN_PASSWORD` del `.env` real (el
   valor por defecto `admin` es solo para desarrollo local).
3. **Canal real de alertas**: decidir email o Slack, y sustituir el receptor `null` de
   `infrastructure/alertmanager/alertmanager.yml` por uno real (hay un ejemplo comentado de
   `email_configs` en el propio fichero).
4. **Alerta de expiración de certificados TLS**: añadir un job de `blackbox_exporter` sondeando el
   dominio real (`setex-facturas.autoken.es` u otro) una vez exista Caddy/TLS real de S4.6 — no
   existe todavía nada que sondear.
5. **Verificación de extremo a extremo**: comprobar que Prometheus scrapea la API real, que una
   caída real dispara `AutokenApiDown`, y que Grafana muestra datos reales — nada de esto se puede
   probar sin la VPS desplegada.

## Puertos (solo si se prueba en local/staging)

| Servicio | Puerto | Nota |
|---|---|---|
| Prometheus | 9090 | expuesto para depuración; en la VPS real, detrás del proxy inverso, no a internet |
| Alertmanager | 9093 | ídem |
| Grafana | 3001 (host) → 3000 (contenedor) | ídem |
| node-exporter | sin puerto de host | solo accesible por la red interna de compose |

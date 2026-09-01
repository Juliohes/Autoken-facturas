# ADR-0020: despliegue público fail-closed con perfil proxy

## Estado

Aceptado — 26/08/2026

## Contexto

La pila Docker se separa en un Compose base y un overlay de despliegue. El base es útil para desarrollo,
pero no conecta API y frontend a la red externa `proxy` ni declara routers Traefik. Un despliegue público
realizado accidentalmente solo con el fichero base dejó al frontend sirviendo `index.html` para `/api/*`.
El navegador veía HTTP 200, pero el login no podía funcionar porque las llamadas nunca llegaban a
FastAPI. Reiniciar Traefik recuperó los routers después de relanzar los servicios correctamente, pero
reiniciar un proxy no debe ser la solución habitual ni una condición oculta del despliegue.

## Decisión

1. `infrastructure/docker-compose.yml` fija `DEPLOYMENT_PROFILE=standalone` para API y worker.
2. `infrastructure/docker-compose.prod.yml` sobreescribe ese valor a `proxy` y añade la red externa,
   los routers y los servicios Traefik.
3. `Settings` falla de forma explícita si `APP_ENV` es `staging` o `production` y el perfil no es `proxy`.
   Desarrollo y carga aislada conservan el perfil `standalone`.
4. `infrastructure/deploy.sh` es el único entrypoint documentado para un despliegue público. Valida el
   fichero Compose combinado, la red `proxy`, el perfil de API, las etiquetas Traefik y el health JSON
   público, usando `docker compose up -d --wait`.
5. El runbook y el README no deben recomendar el Compose base para staging/producción.

## Consecuencias

- Omitir el overlay ya no deja una API de staging/producción arrancada silenciosamente.
- Un `docker compose up -d` sigue pudiendo ejecutarse manualmente, pero la aplicación se detiene y el
  script de despliegue no puede declarar éxito hasta que el borde público esté comprobado.
- El reinicio de Traefik no forma parte del flujo normal; solo se necesita si se cambia el proveedor
  Docker externo o se recupera una configuración antigua.
- La comprobación pública requiere DNS, TLS, Traefik y `curl` disponibles en el host de despliegue.

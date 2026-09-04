# Runbook — Rollback de Autofactu

Procedimiento operativo para volver a una versión o comportamiento anterior sin perder datos ni
desactivar las barreras de aislamiento. Se aplica al stack de `infrastructure` en staging o producción.

## Reglas de seguridad

- Registrar hora, síntoma, versión desplegada, migración actual y persona que ejecuta cada paso.
- No borrar contenedores, volúmenes, tenants, facturas ni borradores como respuesta a un incidente.
- No ejecutar `alembic downgrade` sin backup verificado y sin confirmar que la versión anterior entiende
  el esquema resultante.
- No desactivar ClamAV, RLS, rate limits ni la autorización para hacer pasar un smoke test.
- Si hay sospecha de corrupción o borrado de datos, saltar al rollback de datos y no intentar reparar
  escribiendo directamente en las tablas de negocio.

## 1. Contener el incidente

Desde `/opt/app-facturas/infrastructure`, consultar primero el estado sin reiniciar nada:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml logs --tail=200 api worker
```

Si el incidente pertenece a una feature flag, aplicar el rollback funcional descrito en
`r051-rollout-and-rollback.md`: poner el flag afectado a `false`, retirar el tenant de la allowlist si
procede y reiniciar solo `api`/`worker`. Este camino no necesita downgrade y conserva los datos.

## 2. Rollback de versión de aplicación

Usarlo cuando la versión nueva provoca errores y el esquema de base de datos sigue siendo compatible
con la versión anterior.

1. Identificar el tag o digest de la imagen anterior que pasó CI.
2. Confirmar que no hay una migración nueva incompatible con ese código.
3. Detener solo `api` y `worker`, manteniendo Postgres, Redis, MinIO y ClamAV.
4. Reponer las imágenes anteriores mediante el mecanismo de despliegue aprobado, sin reconstruir desde
   una rama sin verificar.
5. Levantar `api` y `worker` y ejecutar las comprobaciones posteriores.

No se debe hacer rollback de código si la versión nueva ya escribió datos que la anterior no puede leer.
En ese caso, mantener la versión compatible, apagar la feature flag si existe y preparar una corrección.

## 3. Rollback de migración

Es una operación excepcional, no el rollback normal de una feature. Antes de tocar el esquema:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml \
  --profile tools run --rm --entrypoint alembic migrate current
```

Generar antes un backup cifrado siguiendo la sección de uso de `backups-restore.md`, con la imagen
`ops` y el fichero de secretos separado previsto para backups. El backup debe conservarse fuera del
host de aplicación y validarse según ese runbook; nunca se deben poner secretos en argumentos.

Con API y worker detenidos, y solo después de aprobar la compatibilidad:

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml stop api worker
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml \
  --profile tools run --rm --entrypoint alembic migrate downgrade <revision_objetivo>
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml up -d api worker
```

Si una migración ya transformó datos o contiene una operación no reversible, no se fuerza el downgrade:
se restaura el backup en una base separada, se comprueba la integridad y se decide una migración de
compensación. El esquema no se arregla manualmente desde una consola SQL.

## 4. Rollback por pérdida o corrupción de datos

1. Aislar el tráfico de escritura mediante el proxy aprobado, sin borrar el volumen original.
2. Conservar logs, métricas y el volumen para investigación.
3. Crear una base de datos destino nueva y vacía.
4. Ejecutar `restore_drill.py` con el último backup válido y comparar recuentos.
5. Repetir el restore drill si falla o si el backup no autentica correctamente.
6. Cambiar el DSN del despliegue a la base restaurada solo tras aprobar la verificación.
7. Arrancar API/worker y ejecutar el smoke test; mantener el original aislado hasta cerrar el incidente.

El procedimiento detallado de cifrado, destino externo y restore está en `backups-restore.md`. Nunca se
practica un restore destructivo directamente sobre la base de producción.

## 5. Comprobaciones posteriores

```bash
docker compose --env-file ../.env -f docker-compose.yml -f docker-compose.prod.yml ps
curl --fail https://<host-publico>/health
curl --fail https://<host-publico>/api/v1/metrics
```

Comprobar también:

- el login de un usuario de prueba y el acceso al tenant correcto;
- una subida sintética que termine en `201` y quede en `pending_ocr`;
- que el worker procesa o recupera el documento sin duplicarlo;
- que el tenant de prueba no puede ver datos de otro tenant;
- que la cola, errores 5xx, rate limit y ClamAV están sanos;
- que las flags y la versión de Alembic coinciden con lo registrado.

El rollback se cierra solo cuando estas comprobaciones quedan anotadas junto con la versión resultante,
la migración, el backup utilizado y cualquier documento afectado.

# R-051: rollout y rollback por fases

R-051 usa flags cerrados en configuración de la aplicación. No existe un diccionario arbitrario de
flags aceptado desde una petición y la allowlist de tenants nunca se devuelve al navegador.

## Flags

```text
SCANNER_V2_ENABLED
CONTINUOUS_CAPTURE_ENABLED
REVIEW_INBOX_ENABLED
DRAFT_AUTOSAVE_ENABLED
PROCESSING_STAGES_ENABLED
OCR_POLICY_V2_ENABLED
SUPPLIER_LEARNING_ENABLED
```

Todos tienen por defecto el comportamiento actual. `SUPPLIER_LEARNING_ENABLED` está conectado al guard
de aprendizaje de proveedores; apagándolo se conservan las confirmaciones, pero no se actualiza el perfil
agregado. `REVIEW_INBOX_ENABLED` y `DRAFT_AUTOSAVE_ENABLED` también tienen gates en API y frontend.
Si `SCANNER_V2_ENABLED` se apaga, la captura conserva la imagen completa y omite OpenCV. Si
`OCR_POLICY_V2_ENABLED` se apaga, el worker usa el primario legacy Gemini 3 Flash, sin fallback ni
consulta a la política versionada. Todos los rollbacks son reversibles y no requieren migración.

## Canary

1. CI y tests locales con la configuración por defecto.
2. Staging con flags y allowlist de prueba.
3. Admin-tech y tenant interno.
4. Una asesoría piloto.
5. Dos asesorías piloto.
6. Ampliación progresiva hasta 25% y después 100%.

La allowlist se configura como JSON en `ROLLOUT_TENANT_ALLOWLIST`, por ejemplo:

```json
["00000000-0000-0000-0000-000000000001"]
```

Cuando la allowlist no está vacía, un flag activo solo se aplica a esos tenants. Un flag apagado
siempre gana, aunque el tenant esté en la allowlist.

## Preflight

En un entorno público, el despliegue debe pasar primero por el entrypoint que valida Traefik:

```bash
HEALTHCHECK_HOSTS=panel-staging.autoken.es,setex.autoken.es bash infrastructure/deploy.sh
```

No continuar con el canario si ese comando falla. Arrancar solo el Compose base en `staging` o
`production` provoca un fallo cerrado de API/worker por `DEPLOYMENT_PROFILE`, en vez de dejar un
frontend aparentemente sano con la API mal enrutada.

Antes de iniciar el canario, ejecutar desde `backend/`:

```bash
PYTHONPATH=src python scripts/r051_canary_preflight.py --env-file ../.env --json
```

El proceso termina con código `0` solo si los siete flags están definidos con valores booleanos,
`ROLLOUT_TENANT_ALLOWLIST` es una lista JSON de UUIDs y están presentes `GRAFANA_ADMIN_PASSWORD`,
`DB_ENCRYPTION_MASTER_KEY` y `POSTGRES_APP_PASSWORD`. El informe nunca imprime el valor de un secreto.
Un resultado `ready: true` no sustituye la prueba de conectividad ni el canario funcional.

## Rollback

1. Cambiar el flag afectado a `false` en la configuración del despliegue.
2. Reiniciar únicamente API/worker para cargar la configuración, sin ejecutar downgrade de Alembic.
3. Retirar el tenant de `ROLLOUT_TENANT_ALLOWLIST` si el problema está limitado al canario.
4. Consultar métricas de errores, latencia, cola y proveedor antes de volver a ampliar.

El rollback es funcional: conserva los datos ya escritos y devuelve el flujo anterior. No borra
facturas, borradores ni perfiles y no deshace migraciones compatibles.

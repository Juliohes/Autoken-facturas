# R-050: carga y recuperación OCR

Este procedimiento verifica el escenario mínimo de la especificación maestra:

```text
10 usuarios x 10 facturas = 100 uploads
```

La prueba debe ejecutarse en staging con usuarios, empresa, Postgres, Redis, MinIO y antivirus de
prueba. No usar facturas reales ni credenciales reales. El worker OCR debe usar un proveedor de
prueba controlado o un doble que permita observar timeout, `429` y recuperación sin coste externo.

## Preparación

1. Crear un tenant de carga con diez usuarios `user`, una empresa y diez `company_id` válidos en un
   fichero local fuera del repositorio.
2. Comprobar que `DB_POOL_SIZE + DB_MAX_OVERFLOW` cabe en el `max_connections` de Postgres,
   contando todos los procesos y réplicas.
3. Arrancar API, worker, Postgres, Redis, MinIO y antivirus de staging.
4. Confirmar que el benchmark de laboratorio está apagado y que el proveedor OCR de la prueba no es
   producción.

## Ejecución

Desde `backend/`:

```bash
python scripts/r050_load_test.py \
  --config /ruta/local/r050-users.json \
  --out /ruta/local/r050-report.json
```

El script realiza 100 peticiones concurrentes, mide latencia de `POST /uploads`, espera los estados
OCR, consulta `/metrics` y pide la bandeja privada de cada usuario. El informe solo contiene conteos,
latencias, estados y métricas agregadas.

Para probar una caída durante la oleada, usar `r050_recovery_load.py` con un fichero `--ready-file`.
La marca se crea después de completar los diez logins; detener Redis solo después de que aparezca, para
no confundir un fallo de preparación con un fallo durante las subidas:

```bash
python scripts/r050_recovery_load.py \
  --config /ruta/local/r050-users.json \
  --out /ruta/local/r050-recovery-report.json \
  --ready-file /ruta/local/r050-recovery-ready \
  --stagger-seconds 0.5
```

## Criterios de aceptación

- 100 respuestas `201`, salvo `429` previamente justificados por la política de rate-limit.
- `p50` y `p95` de upload registrados; objetivo inicial de `p95 <= 3 s` en red razonable.
- `cross_user_leaks == 0`.
- Informe con `autoken_db_pool_*`, `autoken_ocr_queue_depth` y
  `autoken_ocr_queue_backend_up`.
- Para investigar latencia, conservar también `autoken_upload_phase_seconds_count` y
  `autoken_upload_phase_seconds_sum` por fase; las fases aceptadas están cerradas en el código y no
  contienen identificadores de negocio.
- Estados OCR terminales o timeout explícito, sin perder documentos aceptados.
- Ningún benchmark experimental ejecutado con el laboratorio apagado.

## Recuperación

1. Ejecutar una tanda de carga con Redis operativo y conservar el informe.
2. Interrumpir Redis después de aceptar varias subidas. La API debe seguir devolviendo `201` para
   documentos que ya hayan pasado el rate-limit; el encolado OCR queda pendiente y se registra sin
   datos de factura.
3. Restaurar Redis y ejecutar el recuperador OCR. Verificar que los documentos pendientes vuelven a
   aparecer en la cola y que el claim impide dos llamadas simultáneas al proveedor.
   Para simular específicamente un enqueue perdido, limpiar solo la base Redis dedicada a la prueba
   después de restaurarla y antes de ejecutar el recuperador; nunca hacer esto en una base operativa.
4. Repetir la consulta de `/metrics` y conservar los valores antes/después de `up`, profundidad,
   pendientes, procesando, abandonados y fallidos.
5. En un escenario separado, provocar respuestas `429` del proveedor de prueba. Confirmar que el
   circuito/fallback deja el documento en un estado recuperable y no registra la respuesta cruda ni
   PII.

## Evidencia

Guardar el JSON generado y una nota de ejecución fuera del repositorio de código si contiene URLs,
usuarios o configuración de staging. En el repositorio solo debe quedar el resumen sin PII: p50, p95,
conteos HTTP, conteos OCR, estado del pool, Redis, recuperación, fugas y diagnóstico agregado por fase.

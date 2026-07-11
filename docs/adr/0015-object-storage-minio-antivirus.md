# ADR-0015: Object storage con MinIO (bucket por tenant) y antivirus fail-closed en el intake

- **Estado**: aceptado
- **Fecha**: 2026-07-11
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: ADR-0001 (RLS de dos niveles + audit_log), ADR-0013 (RBAC + scoping por empresa),
  spec `docs/specs/S2.1-upload-seguro.md`, PLAN MAESTRO §11; tarea S2.1

## Contexto
El empleado de una empresa cliente captura una factura (foto o PDF) y la sube a la plataforma. Antes
de llegar al OCR (S2.3) el fichero tiene que entrar de forma **segura y trazable**: guardado en un
almacenamiento aislado por asesoría, comprobado que es realmente una imagen o un PDF (no un
ejecutable disfrazado), pasado por antivirus, dentro de un tamaño razonable y sin colar dos veces la
misma factura de la misma empresa. La regla dura, igual que en `companies`, es **"entero y verificado
o nada"**: nunca un registro sin objeto ni un objeto sin registro, y nunca un fichero sin escanear.

El binario de la factura no cabe en Postgres (ni debe): necesita un **object storage**. Y el intake
es la puerta por la que entra contenido no confiable del exterior, así que necesita **verificación de
tipo real** y **antivirus** antes de persistir nada.

## Decisión

### 1. Object storage: MinIO, un bucket por tenant
Se adopta **MinIO** (S3-compatible, self-hosted, coherente con ADR-0005 Docker vs AWS) como almacén
de objetos. El aislamiento entre asesorías se lleva al almacén con un **bucket por tenant**:

- Bucket: `tenant-{tenant_id}`; clave del objeto: `{company_id}/{sha256}`.
- El bucket del tenant es la **frontera de aislamiento** en el almacén, análoga a la RLS por
  `tenant_id` en la BD: un objeto de una asesoría vive en **su** bucket, nunca en el de otra
  (anti-cruce). El SDK se usa desde funciones de módulo (`storage.put_object/object_exists/
  remove_object`) para poder inyectar fallos en test.
- El registro `uploaded_files` (con `storage_bucket`/`storage_key`, MIME real, `sha256`, tamaño,
  `status=pending_ocr`, `scan_status=clean`) vive en Postgres bajo **RLS de dos niveles**
  (`app.tenant_id` + `app.company_id`), el mismo patrón que `companies` (ADR-0001, migración 0004):
  el `tenant_admin` (sin `company_id`) ve todo su tenant y el `user` queda acotado a su empresa
  también en el motor. La no-duplicación por empresa la garantiza un **UNIQUE `(company_id, sha256)`**
  en BD (resistente a concurrencia), no solo un `SELECT` previo.

### 2. El tipo se decide por el MIME real (bytes), no por el declarado
La aceptación/rechazo de tipo se toma **solo** con el número mágico de los bytes (`filetype`), nunca
con la extensión del nombre ni con la cabecera `Content-Type` del cliente. Solo se admiten
`image/jpeg`, `image/png`, `application/pdf`; cualquier otro MIME real -> 415. Un ejecutable
renombrado a `.jpg` con `Content-Type: image/jpeg` se detecta por lo que es y se rechaza.

### 3. Antivirus fail-closed
Todo fichero se escanea **antes** de almacenarse. Si el antivirus **no está disponible**, la subida
se **rechaza** (503): ningún fichero entra sin escanear. Se descarta explícitamente el fail-open
("si el AV no responde, dejar pasar"). Dos backends tras la misma interfaz (`scanner.scan`):

- **`SignatureScanner`** (dev/CI): en proceso, sin red; detecta la cadena de prueba estándar
  **EICAR**. Permite ejercer el gate en tests y CI sin depender del daemon ni de la red.
- **`ClamdScanner`** (producción): ClamAV real vía el daemon `clamd`; si no conecta ->
  `ScannerUnavailable` (fail-closed), nunca "limpio por defecto".

Selección por `settings.virus_scanner_backend`; sin fijar, `signature` fuera de producción y `clamd`
en producción.

### 4. Orden de validación y atomicidad
El orden importa para los códigos y para no hacer trabajo de más: pertenencia (403/404) -> tamaño
(413) -> MIME real (415) -> SHA-256 -> **dedup por empresa** (409, antes del antivirus) -> antivirus
(422 infectado / 503 caído) -> almacenar objeto (503 si el almacén cae) -> insertar registro + escribir
`audit_log` (`intake.upload`) **en la misma transacción**. Compensación anti-huérfano: si falla el
almacenamiento no hay fila; si falla el registro tras subir el objeto, se **borra** el objeto. La
carrera de dos subidas concurrentes del mismo fichero la reabsorbe el UNIQUE `(company_id, sha256)`:
una responde 201 y la otra 409 con `duplicate_of` (nunca dos filas, nunca un 500).

### 5. Infraestructura
`minio` y `clamav` se añaden a `infrastructure/docker-compose.yml`; la app se configura por env
(`MINIO_*`, `VIRUS_SCANNER_BACKEND`, `CLAMAV_*`). En CI se levanta **MinIO** como service container y
se usa el scanner de firma (ClamAV no hace falta: EICAR en proceso + monkeypatch del daemon caído).
Los secretos (`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`) llegan por env var en el VPS (§9.1), nunca al repo.

## Alternativas consideradas
- **Guardar el binario en Postgres (bytea/large object)**: hincha la BD, encarece backups y no aporta
  aislamiento. Descartado; el object storage es la herramienta correcta.
- **AWS S3 gestionado**: contradice ADR-0005 (self-hosted Docker durante el desarrollo). MinIO da la
  misma API S3 sin atar la infra a un proveedor; migrar a S3 real es un cambio de endpoint/credenciales.
- **Un solo bucket compartido con prefijo por tenant**: pierde la frontera de aislamiento física; una
  política de acceso mal puesta cruzaría asesorías. El bucket por tenant hace el aislamiento explícito
  y auditable, y habilita políticas/cifrado/retención por asesoría en el futuro.
- **Decidir el tipo por `Content-Type`/extensión**: trivial de falsificar; abre la puerta a subir un
  ejecutable como "imagen". El MIME real por bytes es la única señal fiable.
- **Antivirus fail-open**: dejar pasar cuando el AV no responde. Inaceptable: un fichero sin escanear
  no debe persistir. Se elige fail-closed (503 y reintento).

## Consecuencias
- (+) El aislamiento entre asesorías se extiende al almacén (bucket por tenant), coherente con la RLS.
- (+) Contenido no confiable se filtra por tipo real + antivirus antes de tocar el almacén o la BD;
  nunca hay objetos huérfanos ni registros sin objeto ni ficheros sin escanear.
- (+) La no-duplicación por empresa es resistente a concurrencia (UNIQUE en BD, no solo `SELECT`).
- (−) Dos dependencias de infra nuevas (MinIO, ClamAV) que operar y monitorizar; ClamAV descarga la
  base de firmas al arrancar (arranque lento la primera vez).
- (−) El fail-closed del antivirus convierte una caída de ClamAV en rechazos 503 de las subidas: es el
  compromiso aceptado (seguridad sobre disponibilidad del intake), mitigable con HA del daemon.
- (−) El borrado del objeto es la compensación de "registro sin objeto" cuando falla el insert; un
  fallo simultáneo del borrado dejaría un huérfano raro (best-effort), aceptable y acotado.

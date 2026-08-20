# Recorrido completo de una factura en Autoken Facturas v2

> Documento de dominio y arquitectura. Describe paso a paso el ciclo de vida completo de un documento
> (factura recibida o emitida), desde la captura en el móvil hasta su archivo, exportación o purga,
> detallando los datos procesados, almacenamiento, cifrado y salvaguardas de seguridad en cada etapa.

---

## Índice de fases

1. [Fase 1 — Captura y normalización en el dispositivo (Frontend / PWA)](#fase-1--captura-y-normalización-en-el-dispositivo-frontend--pwa)
2. [Fase 2 — Subida segura, validación y almacenamiento (API / Intake)](#fase-2--subida-segura-validación-y-almacenamiento-api--intake)
3. [Fase 3 — Procesamiento asíncrono con IA y arbitraje (Worker / OCR)](#fase-3--procesamiento-asíncrono-con-ia-y-arbitraje-worker--ocr)
4. [Fase 4 — Comprobación, edición auditada y confirmación (Panel / Invoicing)](#fase-4--comprobación-edición-auditada-y-confirmación-panel--invoicing)
5. [Fase 5 — Explotación, exportación, ciclo de vida y purga (Reporting / Platform)](#fase-5--explotación-exportación-ciclo-de-vida-y-purga-reporting--platform)

---

## Fase 1 — Captura y normalización en el dispositivo (Frontend / PWA)

* **Dónde ocurre**: Dispositivo móvil del empleado (Android / iPhone) o navegador de escritorio.
* **Actor**: Rol `user` (empleado de la empresa cliente) o `tenant_admin` (administrador de la asesoría).

### Pasos
1. **Selección de empresa y dirección**: El usuario elige para qué empresa del grupo sube el documento y si la factura es **Recibida** (proveedores) o **Emitida** (clientes).
2. **Activación de la cámara o selector**:
   - Cámara trasera con preferencia de resolución alta (`ideal`, C1 de S6.14).
   - Detección automática del documento (OpenCV.js WASM): detecta esquinas, aplica umbral de Otsu (C3), cierre morfológico y recorta/endereza a un rectángulo "de frente", garantizando un suelo mínimo de resolución de 2200px en el lado largo (C2).
   - Alternativa: selector de fichero nativo del dispositivo (subida directa de PDF o imagen).
3. **Métrica de nitidez (C8)**: Se calcula la varianza del Laplaciano en cliente. Viaja como metadato no bloqueante (`sharpness_score`) para telemetría.
4. **Normalización**: La imagen se convierte a un Blob JPEG comprimido (máxima calidad visual sin sobrecargar el ancho de banda).

---

## Fase 2 — Subida segura, validación y almacenamiento (API / Intake)

* **Dónde ocurre**: Backend FastAPI (`POST /api/v1/uploads` o `/batch`).
* **Seguridad y Aislam习to**: Aislamiento por tenant (RLS de dos niveles: `tenant_id` en el esquema de BD y `company_id` por membresía del usuario).

### Pasos
1. **Verificación de pertenencia (403/404)**: La API comprueba que el usuario pertenece a la asesoría y tiene acceso a la empresa seleccionada (`authorize_file_access`).
2. **Validación estructural**: Se comprueba que los bytes recibidos son realmente un JPEG, PNG o PDF válido (inspección de magic bytes, no solo cabecera HTTP).
3. **Antivirus (ClamAV)**: El fichero pasa por un escaneo sincrónico contra ClamAV. Si da positivo o falla el daemon (fail-closed, ADR-0005), se rechaza de inmediato (422/503).
4. **Deduplicación por huella (SHA-256)**: Se calcula el hash del fichero. Si ya fue subido antes para esa empresa, se rechaza de inmediato (409 `duplicate_of`) para evitar duplicados accidentales.
5. **Almacenamiento cifrado (MinIO)**: El fichero original se sube a un bucket privado de MinIO (`autoken-storage`) cifrado en reposo (AES-256), con una ruta derivada del tenant y de la empresa.
6. **Registro en base de datos**: Se inserta un registro en la tabla `uploaded_files` con estado inicial `pending_ocr`.
7. **Encolado best-effort**: Se encola la tarea `run_ocr_task` en Redis vía arq. La API responde inmediatamente al usuario con un `201 Created` y el ID del fichero.
8. **Liberación del slot del worker (S6.15 C1)**: El worker procesa la lectura principal y encola la comparativa experimental como una tarea aparte, quedando libre al instante para la siguiente factura.

---

## Fase 3 — Procesamiento asíncrono con IA y arbitraje (Worker / OCR)

* **Dónde ocurre**: Contenedor Worker de arq (fondo, asíncrono).
* **Dependencias**: Modelos de IA (Gemini 3 Flash por defecto), motor de reglas puros (`ocr.analysis`).

### Pasos
1. **Descarga en paralelo (S6.15 C3)**: Si es un documento multipágina (S6.12), las páginas se descargan de MinIO simultáneamente (`asyncio.gather`), conservando estrictamente el orden.
2. **Lectura por IA (Fan-out / Extractor)**: Se envía la imagen al proveedor (Gemini Flash). El proveedor devuelve los campos de oro estructurados (fecha, importes, número de factura, tramos de IVA y contraparte) junto con las confianzas separadas para el CIF (`value_confidence`) y para el nombre de la contraparte (`name_confidence`, S6.14 C4).
3. **Árbitro por campo (`reconcile`)**: Si hubiera varios motores (experimentos de ranking), el árbitro combina las lecturas campo a campo priorizando la mayor confianza.
4. **Análisis de dominio y reglas de negocio (`analyze_invoice`)**:
   - **Verificación de CIF propio**: Se comprueba si el CIF conocido de la empresa aparece entre los leídos.
   - **Validaciones deterministas (C6)**: Se aplica el dígito de control del CIF (mód-23, `ocr/verification.py`) y el cuadre aritmético de bases + IVA = total. Si una validación falla, **degrada la confianza mostrada a "baja"** para alertar al humano, sin alterar la lectura original del motor (trazabilidad).
   - **Detección de captura ilegible (C7)**: Si los tres campos fundamentales (fecha, total, contraparte) están vacíos a la vez, o el 100% de los campos con valor tienen confianza "baja", el fichero transiciona a `capture_unreadable` (estado especial: la foto es ilegible, requiere repetir la captura, no revisar campos vacíos).
   - **Enrutado de estado**: Si todo es alto y válido → `ocr_done`. Si hay algún campo dudoso, falta el CIF propio o una validación falla → `needs_review`. Si es captura ilegible → `capture_unreadable`.
5. **Persistencia atómica**: Se guarda la extracción en `ocr_extractions` (ligada al `uploaded_file_id`) y se actualiza el estado del fichero en la misma transacción.

---

## Fase 4 — Comprobación, edición auditada y confirmación (Panel / Invoicing)

* **Dónde ocurre**: Frontend React (PWA) + Backend FastAPI (`invoicing`).
* **Actor**: Rol `user` o `tenant_admin`.

### Pasos
1. **Polling adaptativo (S6.15 C2)**: La pantalla de confirmación consulta el estado del fichero (`GET /uploads/{file_id}/review`). Lo hace de forma adaptativa (cada 0.5s los primeros intentos, luego cada 1.5s) para detectar el resultado tan pronto como el worker termina, sin saturar el servidor.
2. **Manejo de estados especiales**:
   - Si el worker sigue procesando (409 `PendingOcr`): la pantalla muestra un indicador "Procesando factura con IA…" y sigue esperando.
   - Si la foto es ilegible (409 `CaptureUnreadable`, C7): la pantalla redirige automáticamente a la cámara con el mensaje *"La foto no se pudo leer. Repite la captura"* (nunca abre un formulario vacío).
3. **Pantalla de revisión / comprobación**:
   - Se muestran los campos leídos con celdas de color según su confianza (verde = alta, amarillo = dudoso/revisar, rojo = no leído).
   - Se muestra un aviso no bloqueante si la nitidez de cliente era baja (C8).
   - El usuario (o el administrador) revisa, corrige importes, selecciona el proveedor (o lo crea en el supplier master) y ajusta los tramos de IVA.
4. **Confirmación y guardado (`POST /confirm`)**:
   - Validación final de servidor (CIF propio presente, contraparte válida, responsabilidad aceptada).
   - **Persistencia atómica (spec §4)**: Se crea la factura definitiva en la tabla `invoices`, se guardan los tramos de impuesto, se registra el evento en `invoice_edits` (si hubo cambios respecto a la IA), se actualiza el supplier master (`counterparties`) y se marca el fichero original como `confirmed`.
   - Se encola el benchmark de calidad OCR en segundo plano (`run_ocr_benchmark_task`, S6.7).

---

## Fase 5 — Explotación, exportación, ciclo de vida y purga (Reporting / Platform)

* **Dónde ocurre**: Panel de asesoría (`/panel`), panel de plataforma (`/plataforma`), scripts operacionales.
* **Actor**: `tenant_admin` (asesoría) o `platform_admin` (plataforma).

### Pasos
1. **Panel de asesoría y exportación (S3.1 / S3.2)**: Consulta de facturas con filtros, paginación, edición auditada (S3.3) y exportación masiva a Excel (`.xlsx`) con importes normalizados y comas decimales garantizadas.
2. **Cifrado en reposo por tenant (S5.2)**: Los datos sensibles (CIF y nombre de empresas y contrapartes, celdas de facturas) se cifran en base de datos mediante `pgcrypto` con una clave derivada exclusivamente para ese tenant a partir de la clave maestra del servidor (ADR-0018). Las búsquedas por CIF se resuelven mediante índices ciegos deterministas (HMAC-SHA256).
3. **Ciclo de vida y purga (S4.4 / S4.7)**:
   - Suspensión / reactivación de tenants (bloqueo instantáneo de login sin tocar datos).
   - Exportación completa en ZIP (todas las tablas del tenant + ficheros de MinIO).
   - Borrado seguro o purga atómica de tenants demo (`SELECT ... FOR UPDATE` + `DELETE` en única transacción SQL, migración 0011).
4. **Backups cifrados y simulacros de restauración (S5.3)**: Volcados diarios automáticos cifrados en memoria con AES-256-GCM (`BACKUP_ENCRYPTION_KEY`, ADR-0019, clave independiente de la de los tenants) y enviados por SSH a una VPS de respaldo separada físicamente, verificados periódicamente con `restore_drill.py` contra bases de datos limpias.

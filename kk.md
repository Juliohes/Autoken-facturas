# Flujo completo: foto hasta factura guardada

## Conclusión

El flujo actual tiene tres momentos distintos:

1. **La foto se acepta y se guarda como documento pendiente.**
2. **La IA termina y los datos aparecen en la pantalla de revisión.**
3. **El usuario confirma y se crea la factura definitiva.**

La pantalla de revisión aparece poco después del `201` de la subida, pero los datos no aparecen hasta que termina el OCR y `GET /review` devuelve `200`.

Aviso de versión: he analizado el código actual de la rama `feature/s6-15-quitar-espera-muerta`. S6.15 está en la PR #161, todavía abierta y no mergeada. Por tanto, estas mejoras están en el código de esta rama, pero no se puede asegurar que estén en producción sin verificar la imagen desplegada.

No he ejecutado una subida real contra Gemini porque tendría coste y podría procesar datos reales.

## Flujo Completo

```text
Usuario pulsa "Capturar foto"
    -> captura del frame
    -> análisis y recorte local
    -> conversión a JPEG
    -> POST /api/v1/uploads
    -> validación, antivirus, MinIO y PostgreSQL
    -> 201 + file_id
    -> navegación a /confirmar/{file_id}
    -> GET /review
    -> 409 mientras el OCR trabaja
    -> polling automático
    -> worker termina y guarda la extracción
    -> GET /review devuelve 200
    -> aparece el formulario con los datos OCR
    -> usuario revisa y corrige
    -> pulsa "Confirmar y guardar"
    -> POST /confirm
    -> factura, auditoría y estado confirmado
```

## 1. Preparación De La Cámara

La cámara no se abre automáticamente al entrar en `/capturar`. El usuario debe pulsar `Tomar foto`.

Archivo: `frontend/src/features/capture/CaptureScreen.tsx:260-268`

La aplicación solicita:

- Cámara trasera preferida.
- Resolución ideal de `4096 x 2160`.
- Sin audio.
- Fallback a cualquier cámara si no existe cámara trasera.

Archivo: `frontend/src/features/capture/useCameraStream.ts:57-70`

La petición de permiso tiene un límite de 10 segundos:

```text
CAMERA_REQUEST_TIMEOUT_MS = 10_000
```

Archivo: `frontend/src/features/capture/useCameraStream.ts:5`

Si el usuario tarda en aceptar, el sistema operativo no responde o la cámara falla, la aplicación muestra el fallback de subir archivo.

El botón `Capturar foto` no se habilita hasta que el vídeo tiene dimensiones reales:

```text
videoWidth > 0 && videoHeight > 0
```

Archivo: `frontend/src/features/capture/CaptureScreen.tsx:97-100`

La aplicación actual no hace auto-captura por frames. No espera automáticamente a que la foto esté quieta ni dispara sola. El disparo siempre depende de que el usuario pulse el botón.

## 2. Captura Del Frame

Cuando el usuario pulsa `Capturar foto`:

1. Se comprueba que el vídeo está preparado.
2. Se copia el frame actual a un `canvas`.
3. Se convierte en `ImageData`.
4. Se apaga la cámara y la linterna.
5. Se inicia el procesamiento local.

Archivo: `frontend/src/features/capture/CaptureScreen.tsx:154-180`

La copia del frame ocurre aquí:

`frontend/src/features/capture/grabVideoFrame.ts:4-12`

Con una cámara de alta resolución, un frame de `4096 x 2160` contiene aproximadamente 8,85 millones de píxeles. Eso implica una copia de memoria importante, pero el repositorio no contiene mediciones reales de cuánto tarda en cada móvil.

## 3. Procesamiento Local De Imagen

La aplicación carga OpenCV.js de forma perezosa. Es un módulo WASM de varios megabytes y solo se carga cuando se necesita analizar la imagen.

Archivo: `frontend/src/features/capture/opencv/loadOpenCv.ts:12-31`

En la primera captura de una sesión puede haber:

- Descarga del módulo OpenCV.
- Inicialización del runtime WASM.
- Reserva de memoria del navegador.
- Procesamiento del frame.

En capturas posteriores, OpenCV queda cacheado en memoria.

El análisis realiza dos operaciones:

- Nitidez mediante varianza del Laplaciano.
- Detección de esquinas del documento.

Archivo: `frontend/src/features/capture/analyzeFrame.ts:9-11`

La detección usa:

- Escala de grises.
- Desenfoque gaussiano.
- Umbral Otsu.
- Canny.
- Cierre morfológico.
- Contornos.
- `convexHull`.
- `minAreaRect` como fallback.

Archivo: `frontend/src/features/capture/opencv/documentEdges.ts:78-129`

Si encuentra el documento:

- Recorta.
- Corrige la perspectiva.
- Mantiene un mínimo de 2200 píxeles en el lado largo.
- Genera una imagen rectificada.

Si no encuentra bordes claros, no bloquea al usuario. Sube el frame completo.

Archivo: `frontend/src/features/capture/processCapture.ts:10-14`

Después se convierte a JPEG con calidad `0.85`:

`frontend/src/features/capture/normalizeToJpeg.ts:5-20`

Este procesamiento ocurre antes de la subida y actualmente no tiene instrumentación temporal. No existe un dato fiable de cuánto tarda en Android, iPhone, Chrome o Edge.

## 4. Subida A La API

El frontend construye un `FormData` con:

```text
file = captura.jpg
company_id
direction = recibida | emitida
sharpness_score
```

Archivo: `frontend/src/features/capture/useUploadCapture.ts:77-87`

Llama a:

```http
POST /api/v1/uploads
```

La petición incluye el JWT. Si recibe `401`, intenta renovar el token y repite la subida una vez:

`frontend/src/api/client.ts:28-45`

No hay un timeout propio del frontend para esta petición. Depende del navegador, red, proxy y API.

## 5. Validación Y Almacenamiento

La API no manda todavía la imagen a la IA. Primero valida y almacena el documento.

Orden real en `create_upload()`:

1. Comprueba que no esté vacío.
2. Detecta el MIME real a partir de los bytes.
3. Valida que la imagen sea decodificable.
4. Comprueba dimensiones máximas.
5. Calcula SHA-256.
6. Comprueba duplicados.
7. Ejecuta el antivirus.
8. Sube el objeto a MinIO.
9. Inserta `uploaded_files`.
10. Escribe la auditoría de subida.
11. Hace commit de PostgreSQL.
12. Encola el OCR después del commit.

Archivo: `backend/src/invoice_intake/service.py:343-400`

Límites actuales:

```text
Fichero individual: 15 MiB
Imagen decodificada: 40 millones de píxeles
Cuerpo HTTP: 16 MiB
```

Configuración: `backend/src/shared/config.py:289-301`

El antivirus de producción es ClamAV y funciona fail-closed. Si ClamAV no responde, la subida falla con `503` y no se almacena el fichero.

Archivo: `backend/src/invoice_intake/scanner.py:63-79`

El objeto se guarda en MinIO antes de insertar la fila de base de datos. Si PostgreSQL falla, la aplicación intenta borrar el objeto para no dejar basura.

El estado inicial queda:

```text
pending_ocr
```

La subida no espera a Gemini.

## 6. Cuándo Aparece La Pantalla De Revisión

Cuando la API devuelve `201`, el backend devuelve el `file_id`.

El frontend navega inmediatamente a:

```text
/confirmar/{fileId}
```

Archivo: `frontend/src/app/AppRoutes.tsx:87-97`

En ese momento aparece la pantalla de confirmación, inicialmente con:

```text
Leyendo la factura...
```

Esto significa que hay dos tiempos diferentes:

| Momento | Qué ve el usuario |
|---|---|
| Después del `201` | Pantalla de revisión con indicador de espera |
| Después del OCR | Formulario con datos reales para revisar |

La aplicación no muestra una vista previa intermedia de la foto para que el usuario la apruebe antes de subirla. La revisión visual de la imagen no existe como paso separado. La revisión actual es la revisión de los datos extraídos por la IA.

## 7. Encolado Del OCR

Después del commit de la subida, la API intenta encolar:

```text
run_ocr_task(tenant_id, company_id, file_id)
```

Archivo: `backend/src/invoice_intake/service.py:597-614`

La cola es Redis mediante arq:

```text
autoken:queue:ocr
```

Archivo: `backend/src/jobs/queue.py:74-89`

El encolado es best-effort:

- Si Redis funciona, el trabajo entra en la cola.
- Si Redis falla, la subida sigue siendo válida.
- El fichero permanece en `pending_ocr`.
- El recuperador periódico intenta volver a encolarlo.

El recuperador se ejecuta cada minuto:

`backend/src/jobs/worker.py:74-84`

Esto significa que, si falla el primer encolado, existe una espera adicional de hasta aproximadamente un ciclo de recuperación, más la espera normal de la cola.

No hay una garantía temporal máxima para la espera en Redis o en la cola.

## 8. Inicio Del Worker

El worker reclama el documento con un token temporal:

```text
pending_ocr -> processing
```

El lease actual es:

```text
300 segundos
```

El claim evita que dos workers procesen la misma factura a la vez y utiliza un token de fencing para impedir que un worker antiguo sobrescriba el resultado de otro.

Archivos:

- `backend/src/jobs/ocr.py:93-121`
- `backend/src/invoice_intake/repository.py:196-260`

Antes de llamar a Gemini, el worker:

- Carga las páginas del documento.
- Carga la empresa.
- Obtiene el CIF propio.
- Lee el interruptor del experimento OCR.
- Cierra la primera sesión de PostgreSQL.

La sesión no permanece abierta durante la llamada lenta al proveedor.

## 9. Descarga Desde MinIO

Para una factura de una página, se descarga una imagen.

Para una factura multipágina:

- Las páginas se descargan en paralelo.
- Se conserva el orden original.
- El tiempo se aproxima al de la página más lenta, no a la suma de todas.

Archivo: `backend/src/jobs/ocr.py:61-75`

Las descargas de MinIO no tienen un timeout de aplicación propio. Dependen de la red, MinIO y el cliente SDK.

## 10. Lectura De Gemini

El motor principal actual es:

```text
Gemini 3 Flash
```

El worker envía todas las páginas en una sola petición y solicita JSON estructurado:

`backend/src/ocr/engines/gemini_extractor.py:80-103`

El resultado contiene, entre otros:

- Fecha.
- Número de factura.
- Base imponible.
- IVA.
- Total.
- IRPF.
- CIF de contraparte.
- Nombre de contraparte.
- Tramos de IVA.
- Confianza independiente de cada campo.

La llamada está limitada a:

```text
150 segundos
```

Archivo: `backend/src/jobs/ocr.py:123-145`

El timeout total de arq es:

```text
180 segundos
```

Archivo: `backend/src/jobs/worker.py:63-72`

Si Gemini no responde:

```text
processing -> ocr_failed
```

No se persiste una extracción parcial. El usuario debe reintentar el OCR desde el historial.

## 11. Arbitraje Y Reglas

Después de Gemini:

1. Se valida el JSON.
2. Los campos ilegibles se convierten en `null`.
3. Las confianzas se normalizan.
4. El árbitro reconcilia lecturas.
5. Se analiza la factura con reglas deterministas.
6. Se comprueba el CIF propio.
7. Se valida el CIF de contraparte.
8. Se comprueba el cuadre matemático.
9. Se decide el estado.

Archivo: `backend/src/ocr/analysis.py:77-157`

Estados resultantes:

| Resultado | Estado del fichero |
|---|---|
| Lectura válida | `ocr_done` |
| Hay datos dudosos | `needs_review` |
| Imagen ilegible | `capture_unreadable` |
| Error de proveedor o infraestructura | `ocr_failed` |

Tanto `ocr_done` como `needs_review` llegan a la pantalla de revisión. La aplicación siempre deja que el humano vea y revise los datos.

La captura ilegible no abre un formulario vacío. Redirige a `/capturar` para repetir la foto.

## 12. Persistencia Del Resultado OCR

El worker abre una segunda transacción corta y guarda:

- Extracción OCR.
- Confianzas.
- Validaciones.
- Datos de contraparte.
- Motor y modelo.
- Respuesta cruda para trazabilidad.
- Estado lógico de la lectura.
- Nuevo estado del fichero.
- Limpieza del claim.

Archivo: `backend/src/jobs/ocr.py:147-182`

La escritura de `ocr_extractions` y el cambio de estado se hacen de forma atómica.

El momento decisivo es:

```text
upsert ocr_extractions
+
finish_claim
+
commit PostgreSQL
```

A partir de ese commit, la revisión ya puede devolver los datos.

## 13. Polling De La Pantalla

La pantalla consulta:

```http
GET /api/v1/uploads/{file_id}/review
```

Archivo frontend:

`frontend/src/features/confirmation/useReview.ts:34-59`

Mientras el fichero está en:

```text
pending_ocr
processing
```

el backend devuelve:

```http
409
```

con:

```text
La factura todavía se está procesando con IA
```

El frontend reconoce ese `409` como transitorio y reintenta.

Configuración actual:

```text
Primeros 5 reintentos: 500 ms
Después: 1.500 ms
Sin límite total mientras siga procesándose
```

Archivo: `frontend/src/features/confirmation/useReview.ts:61-67`

Por tanto, una vez que el worker termina y hace commit:

- El usuario puede detectar el resultado entre 0 y 500 ms en los primeros intentos.
- Después puede tardar entre 0 y 1.500 ms en detectarlo.

El primer `GET /review` se lanza al montar la pantalla. No espera deliberadamente antes de preguntar.

## 14. Construcción De La Revisión

Cuando el backend ve `ocr_done` o `needs_review`:

1. Autoriza el fichero.
2. Lee `ocr_extractions`.
3. Descifra los datos sensibles.
4. Verifica de nuevo el CIF de contraparte.
5. Carga la empresa propia.
6. Calcula avisos.
7. Calcula bloqueos.
8. Devuelve los datos.

Archivo: `backend/src/invoicing/service.py:391-469`

La respuesta contiene:

```text
fields
confidences
counterparty_verdict
own
warnings
blocking_reasons
direction
```

La pantalla monta el formulario solo cuando recibe esa respuesta:

`frontend/src/features/confirmation/ConfirmationScreen.tsx:44-107`

Los campos se muestran en cuatro bloques:

- Contraparte.
- Importes.
- Fecha y número.
- Identidad propia.

El IRPF aparece separado del IVA y se resta en el cuadre:

```text
base imponible + IVA - IRPF = total
```

## 15. Verificación Del CIF En La Revisión

La revisión puede ser muy rápida si el CIF ya está en el supplier master del tenant.

Si no está, el servicio puede consultar fuentes externas habilitadas:

- AEAT.
- VIES.
- BORME.

Cada fuente tiene un timeout de 10 segundos y se consultan secuencialmente si procede.

Archivo: `backend/src/counterparty/service.py:114-226`

En el peor caso teórico con tres fuentes habilitadas:

```text
hasta aproximadamente 30 segundos
```

En la práctica:

- CIF inválido: no hay llamada externa.
- CIF ya conocido: lectura local.
- CIF cacheado: lectura de caché.
- CIF no conocido: puede haber espera de red.
- Una fuente no configurada se salta.

Este tiempo forma parte del `GET /review` que finalmente devuelve los datos al usuario.

## 16. Qué Puede Hacer El Usuario

Una vez visible el formulario, el usuario puede:

- Revisar los campos.
- Corregir importes.
- Corregir fecha.
- Corregir número.
- Editar el CIF y nombre.
- Revisar los tramos de IVA.
- Revisar el IRPF.
- Aceptar responsabilidad.
- Confirmar la factura.

Si modifica el CIF o el nombre, el frontend espera 300 ms después de la última tecla antes de lanzar una verificación:

`frontend/src/features/confirmation/useDraftCounterpartyVerdict.ts:18-41`

La edición humana no tiene un tiempo técnico fijo. Es el tramo más variable de todo el flujo.

## 17. Guardado Definitivo

Al pulsar `Confirmar y guardar`, el frontend llama a:

```http
POST /api/v1/uploads/{file_id}/confirm
```

Archivo: `frontend/src/features/confirmation/useConfirm.ts:43-59`

El backend vuelve a comprobar todo, aunque el frontend ya lo haya comprobado:

1. El fichero pertenece al usuario.
2. El estado permite confirmarlo.
3. No existe ya una factura para ese fichero.
4. El usuario acepta la responsabilidad.
5. Se cumplen las reglas del CIF propio.
6. Se verifica otra vez la contraparte.
7. Se calcula el cuadre.
8. Se inserta la factura.
9. Se insertan los tramos de IVA.
10. Se guardan las correcciones.
11. Se escribe la auditoría.
12. Se marca el fichero como `confirmed`.
13. Se actualiza el supplier master.

Archivo: `backend/src/invoicing/service.py:492-628`

La factura queda completamente guardada cuando esa transacción hace commit y el endpoint devuelve `201`.

El benchmark posterior de OCR se encola después y no bloquea el guardado:

`backend/src/invoicing/service.py:625-647`

## Tiempos Disponibles

| Tramo | Tiempo conocido |
|---|---:|
| Solicitud de cámara | Límite de 10 s |
| Carga inicial de OpenCV | No medida, solo primera captura |
| Captura y procesamiento local | No medido |
| Subida, validación y almacenamiento | `p95 = 2,59 s` en test de 50 subidas concurrentes |
| Navegación a `/confirmar` | Inmediata después del `201` |
| Espera de cola | No medida, sin límite fijo |
| Recuperación tras fallo de Redis | Recuperador cada minuto |
| Descarga multipágina | Paralela, sin medición real |
| Gemini Flash, benchmark histórico | Media 21,466 s, mediana 20,556 s, máximo 31,336 s |
| Gemini Flash, medición de producción documentada | Aproximadamente 15 s de media, pico de 52 s |
| Timeout de Gemini | 150 s |
| Detección por polling | 0-500 ms al principio, 0-1.500 ms después |
| Verificación CIF externa | Hasta 10 s por fuente, hasta aproximadamente 30 s teóricos |
| Guardado final | No hay medición aislada |
| Revisión humana | Tiempo indefinido |

El test de carga de `2,59 s` mide solamente `POST /uploads`. No incluye:

- OpenCV.
- Espera de Redis.
- OCR.
- Persistencia de extracción.
- Polling.
- Verificación del CIF.
- Confirmación final.

Referencia: `docs/specs/S5.5-pruebas-de-carga.md:88-103`

## Estimación Realista

Para una factura de una página, con cola libre y CIF conocido:

```text
Tiempo hasta mostrar el panel con indicador:
    procesamiento local de la foto
  + subida y validación
```

No hay una medición de esos dos componentes juntos.

Tiempo aproximado hasta ver los datos:

```text
procesamiento local
+ aproximadamente 0-2,6 s de intake como referencia de carga
+ espera de cola
+ aproximadamente 15-22 s de Gemini
+ análisis y persistencia
+ 0-1,5 s de polling
+ verificación de contraparte
```

La mejor estimación honesta para condiciones normales es:

```text
aproximadamente 20-30 segundos más el procesamiento local y la cola
```

Pero no es un SLA. En la medición histórica de producción se documentó un pico de proveedor de 52 segundos, por lo que una factura concreta puede tardar bastante más.

Si el proveedor llega al timeout de 150 segundos:

```text
no aparecen datos de revisión
```

La factura queda en `ocr_failed` y debe reintentarse.

## Puntos Importantes

- La aplicación guarda primero la foto y después la procesa. La subida no depende de que Gemini esté disponible.
- El usuario puede ver la pantalla de confirmación antes de que existan los datos.
- El formulario con datos solo aparece después del commit de `ocr_extractions`.
- La revisión OCR no guarda todavía una factura definitiva.
- La factura definitiva solo existe después de `POST /confirm`.
- No existe una medición de extremo a extremo desde el disparo de cámara hasta los datos visibles.
- Las fotos de mayor resolución de S6.14 todavía no tienen un benchmark temporal nuevo.
- La comparativa experimental de S6.15 ya no bloquea el resultado principal, pero utiliza la misma cola OCR. Bajo carga intensa puede competir por slots con otros trabajos.
- El código actual no fija explícitamente en `WorkerSettings` el número de trabajos concurrentes. La capacidad real depende del valor por defecto de arq y de cómo esté ejecutado el worker.
- La documentación histórica de la v1 que habla de 2-5 segundos no aplica a esta v2 asíncrona.

## Qué Haría Para Tener Tiempos Exactos

Para medirlo profesionalmente habría que registrar, sin guardar datos personales, estos instantes:

```text
capture_clicked
jpeg_ready
upload_started
upload_201
ocr_enqueued
ocr_claimed
provider_started
provider_finished
ocr_persisted
review_requested
review_200
confirm_started
confirm_committed
```

Con esos eventos se podrían obtener:

- Tiempo de procesamiento móvil.
- Tiempo de subida.
- Tiempo de espera en cola.
- Tiempo de Gemini.
- Tiempo de persistencia.
- Tiempo de polling.
- Tiempo de verificación CIF.
- Tiempo total hasta datos visibles.
- Tiempo total hasta factura confirmada.

Actualmente la aplicación solo permite aproximarlo con `uploaded_files.created_at` y `ocr_extractions.created_at`, pero eso mezcla cola, worker, red y proveedor. No es un cronómetro exacto.

## En cristiano

La foto se guarda primero en el almacén y en la base de datos. Después un trabajador separado la manda a la IA. Mientras tanto, la pantalla pregunta cada poco tiempo si la IA ya terminó.

Cuando la IA termina, guarda los datos y entonces aparecen en la pantalla. El usuario los revisa y corrige. Solo al pulsar `Confirmar y guardar` se crea la factura definitiva.

Hoy sabemos que la IA suele tardar aproximadamente entre 15 y 22 segundos, pero no tenemos un cronómetro que mida todo el recorrido completo. Por eso el tiempo total real puede ser aproximadamente de 20-30 segundos en condiciones normales, más el tiempo del móvil, la subida y cualquier espera de la cola.

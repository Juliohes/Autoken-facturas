# Estado de Implementación de la Especificación Maestra

Registro operativo de `ESPECIFICACION_MAESTRA_AUTOKEN_AUTOFACTU_PRODUCCION_v3.md`.
Un requisito solo pasa a `DONE` con implementación y evidencia verificable.

| ID | Estado | Dependencias | Evidencia / observaciones |
|---|---|---|---|
| R-000 | VERIFYING | — | Alembic tiene un único head (`0056_r050_ctx`) en el Postgres real del stack. Frontend: 441 tests, typecheck y build pasan; lint conserva solo 2 warnings preexistentes de `SessionProvider`. La reconciliación backend completa sigue pendiente. |
| R-001 | VERIFYING | R-000 | Precedencia recogida en la especificación y la captura existente; falta reconciliación formal. |
| R-002 | VERIFYING | R-001 | La pantalla ofrece factura simple, varias facturas y una factura multipágina; el contrato de captura continua comprueba 3 `file_id` independientes y el flujo multipágina conserva 1 raíz. Falta validación E2E real en dispositivo. |
| R-003 | VERIFYING | R-001 | Tipos de captura existentes; falta auditoría contra la taxonomía maestra. |
| R-004 | VERIFYING | R-003 | `scanner.worker.ts`, `scannerProtocol.ts` y `useScannerEngine.ts`; máximo un análisis en vuelo, descarte de frames ocupados y guardia de resultados obsoletos. Test de comportamiento, suite frontend y build pasan; falta validación en navegador/dispositivo real. |
| R-005 | VERIFYING | R-003 | Detector OpenCV con scoring de área, rectangularidad, convexidad, centrado, continuidad, margen y aspecto; prior de confianza por método. 9 tests OpenCV pasan; falta validación con imágenes reales de dispositivo. |
| R-006 | VERIFYING | R-005 | `qualityGate.ts` puro con razones explícitas para documento, confianza, tamaño, clipping, nitidez, exposición, perspectiva y estabilidad. `qualitySignals.ts` calcula luminancia, clipping y perspectiva; `analyzeFrame.ts` calcula nitidez sobre el ROI del documento y usa la configuración central. El gate rechaza señales no finitas de forma conservadora. 18 tests de comportamiento pasan; falta validación con imágenes de dispositivo real. |
| R-007 | VERIFYING | R-006 | Máquina `AUTO/MANUAL` conectada a `useAutoCapture.ts`: AUTO por defecto, gate de calidad, historial de estabilidad (mínimo 700 ms y 4 frames), confirmación de 350 ms, MANUAL siempre disponible y reset al cambiar de modo. AUTO y MANUAL comparten el `captureLockRef` y el mismo pipeline de captura; el lock se libera también si la cámara falla y AUTO queda deshabilitado durante preview/procesamiento. 11 tests específicos de reducer/hook/estabilidad/UI pasan; falta validación en navegador y dispositivo real. |
| R-008 | VERIFYING | R-005 | `coordinates.ts` compensa explícitamente `object-cover`; `DocumentOverlay.tsx` dibuja guía y polígono SVG con estados. 3 tests de coordenadas, suite frontend y build pasan; falta validación visual en navegador/dispositivo real. |
| R-009 | VERIFYING | R-005,R-007 | `grabVideoFrame.ts` prioriza `ImageCapture.takePhoto()` con fallback canvas; `analyzeFrame.ts` limita la copia de análisis a 1600 px con `OffscreenCanvas` en worker y escala las esquinas al still original. `processCapture.ts` valida finitud, límites, área, clipping, degeneración y perspectiva antes de aplicar el warp; si la geometría no es fiable o OpenCV falla conserva la imagen completa. 8 tests de geometría/fallback y la suite frontend pasan; falta validación en dispositivo real. |
| R-010 | VERIFYING | R-009 | `CapturePreview.tsx` obliga a revisar la captura individual antes del POST, con `Repetir`, `Usar foto`, estados de guardado y limpieza de Blob URL. 3 tests de preview y suite frontend pasan; falta validación visual en dispositivo real. |
| R-011 | VERIFYING | R-010 | `uploadCapture` y `uploadMultipageCapture` separan el transporte de los hooks TanStack Query; frontend acepta solo `201` con `id` y conserva el `409 duplicate_of`; backend declara `201`, deja `pending_ocr` y encola tras commit. 7 tests de contrato/transporte frontend y 441 tests frontend pasan; tests backend requieren Redis local/staging. |
| R-012 | VERIFYING | R-002,R-011 | `continuousCapture.ts` mantiene sesión UX con máximo 10, secuencia y timestamp; cada `201` permite la siguiente subida individual y los duplicados no se agregan dos veces. 4 tests puros y un escenario UI de 3 facturas pasan; falta E2E real con OCR concurrente y dispositivo. |
| R-013 | VERIFYING | R-012 | Migración `0054_r013_capture_session` añade `capture_session_id`, `capture_sequence`, constraint e índice parcial; ORM, `POST /uploads`, query ordenada por sesión y bandeja privada están alineados. El frontend envía UUID y secuencia; integración backend requiere Redis/Postgres. |
| R-014 | VERIFYING | R-011 | `CaptureRoute` muestra aceptación y ofrece `Revisar cuando esté lista` o `Ir a Mis facturas`; no navega automáticamente a `/confirmar/:id`. Test de ruta pasa; falta validación visual real. |
| R-015 | VERIFYING | R-011 | En continuous se conserva el `MediaStream`, se revalida `readyState` y solo se solicita otra cámara si el track ya no está vivo. Test con track vivo demuestra cero reaperturas tras `201`; falta validación en dispositivo. |
| R-016 | DONE | R-000 | Migración `0041_processing_stage`, enum, ORM, timestamps y `queued`. 2 tests de integración pasan. |
| R-017 | DONE | R-016 | Etapas cercadas por `ocr_claim_token`; worker instrumentado. 32 regresiones backend pasan. |
| R-018 | DONE | R-017 | `ProcessingProgress`, modelo puro y tests; textos por etapa, porcentaje monotónico y barra accesible. |
| R-019 | DONE | R-016 | `GET /api/v1/uploads/{file_id}/status`, autorización privada, respuesta sin PII y OpenAPI regenerado. |
| R-020 | DONE | R-019 | Bandeja privada `/mis-facturas`, endpoint SELF ONLY, resumen agregado, cursor compuesto, polling único y UI sin PII. 3 tests backend y 2 frontend pasan. |
| R-021 | DONE | R-000 | Tabla `review_drafts` con RLS FORCE, propietario, revisión y campos fiscales cifrados. Migración `0042_review_drafts`. |
| R-022 | DONE | R-021 | `PUT /api/v1/uploads/{file_id}/draft`, conflicto 409 por revisión obsoleta y autosave frontend con debounce de 750 ms. 3 tests backend y 2 frontend pasan. |
| R-023 | DONE | R-021 | `GET /uploads/{file_id}/review` prioriza `review_drafts`, conserva confidencias OCR y devuelve `source`, revisión, fecha del borrador y `page_count`. 26 tests de confirmación pasan. |
| R-024 | DONE | R-022,R-023 | Confirmación server-side desde el draft, persistencia y borrado del draft en la misma transacción. 31 tests de confirmación/borrador pasan. |
| R-025 | DONE | R-020,R-024 | Post-confirmación invalida inbox, obtiene snapshot fresco, elige primera factura revisable o vuelve a `/mis-facturas`. 3 tests frontend pasan. |
| R-026 | DONE | R-020,R-021 | Panel `/pendientes-equipo`, listado tenant_admin de pendientes ajenos, apertura `review-readonly` y UI sin acciones de escritura. 34 tests backend y 2 frontend pasan. |
| R-027 | DONE | R-020 | Listado global metadata-only con cursor compuesto, paginación UI, apertura explícita read-only exclusiva de `admin-tech` y auditoría con tenant, empresa, actor, request ID e IP sin OCR raw. 4 tests HTTP R-027 y 6 regresiones inbox/supervisión pasan. |
| R-028 | DONE | R-021 | Job diario `purge_expired_unconfirmed_documents`: selección con lock, borrado DB-first, auditoría sin PII, commit y limpieza MinIO best-effort. Métricas durables `expired_pending_count` y `purge_storage_failures`. 2 tests R-028 y 10 regresiones R-026/R-027 pasan. |
| R-029 | DONE | R-000 | Mistral OCR usa `document_annotation` con JSON Schema, valida `InvoiceExtractionSchema` y convierte amounts string a `Decimal` sin confianza auto-confirmable. 36 tests OCR/ranking pasan. |
| R-030 | DONE | R-000 | IDs explícitos `gemini-3.5-flash`, `gemini-3.6-flash` y `gemini-3.5-flash-lite`; producción fijada manualmente a Flash 3.5 y sin `latest`. 18 tests Gemini/ranking pasan. |
| R-031 | DONE | R-029,R-030 | `ocr/schema.py` es el contrato Pydantic común; parser compartido y adapters Gemini, Claude, Azure OpenAI y Mistral traducen a `ExtractedInvoice`, con amounts string y `schema_version`. 43 tests de adapters/parser pasan. |
| R-032 | VERIFYING | R-031 | Contrato comparable R-032 persistido por resultado, cuatro candidatos mínimos separados del ranking histórico, métricas por variante/motor/modelo y endpoint agregado con p50/p95, errores, páginas, coste y correcciones. 64 tests unitarios OCR/adapters pasan; integración requiere Redis disponible. |
| R-033 | VERIFYING | R-032 | `ocr/policy.py`, política persistida desde migración `0048_r033_ocr_policy`, endpoint `admin-tech` `/platform/ocr-policy` y worker OCR leyendo exactamente el primario configurado. Tests unitarios pasan; integración requiere Redis disponible. |
| R-034 | VERIFYING | R-033 | Fallback condicional en `ocr/fallback.py` y `jobs.ocr`: timeout/error, campos críticos ausentes o dudosos, CIF inválido y descuadre; etapa `FALLBACK_OCR`, una sola segunda llamada y `needs_review` si hay conflicto. 4 tests puros pasan; integración requiere Redis/Postgres. |
| R-035 | VERIFYING | R-034 | Consenso por campo en `ocr/arbiter.py`, normalización conservadora en `ocr/normalization.py`, decisiones `accepted`/`uncertain`/`conflict`, fuentes y reason codes en `raw._consensus`; el worker respeta `consensus_mode`. 7 tests de comportamiento pasan; integración requiere Redis/Postgres. |
| R-036 | VERIFYING | R-035 | Score de confianza sistémica explicable en `ocr/confidence.py`, separado de la etiqueta del proveedor, con acuerdo, validaciones, fallback y reason codes persistidos bajo `confidences._system_confidence`. 3 tests R-036 y 22 tests OCR/análisis pasan; integración requiere Redis/Postgres. |
| R-037 | VERIFYING | R-031 | `TaxLineCheck`/`InvoiceMathCheck` detallan cuotas, deltas y total sin romper `CheckResult`; tipos de IVA numéricos desconocidos se conservan y se marcan para revisión mediante política fiscal separada. 90 tests fiscales/OCR pasan; integración requiere Redis/Postgres. |
| R-038 | VERIFYING | R-024,R-037 | Tabla `supplier_profiles` scoped por tenant+empresa+CIF ciego, contadores agregados, cold start de 3 confirmaciones, actualización dentro de la confirmación humana y lectura de evidencia madura para detectar anomalías de IVA/fallback sin sobrescribir OCR. 4 tests puros pasan; integración requiere Redis/Postgres. |
| R-039 | VERIFYING | R-036 | Evidencia local opcional en `ocr/local_evidence/tesseract_checker.py`, con timeout, estado `available`, coincidencias tolerantes y sin invalidar por ausencia. No está en el camino crítico del worker. 3 tests puros pasan. |
| R-040 | VERIFYING | R-032 | Benchmark offline en `ocr/offline_preprocess.py` con variantes `raw`, `natural`, `clahe`, `gray` y `sauvola`, generadas desde el mismo original y reportadas contra un `ground_truth_hash` común. 2 tests puros pasan; no llama proveedores ni entra en producción. |
| R-041 | VERIFYING | R-032 | `PaddleOCRLayoutEngine` y endpoint `/layout` viven en `services/ocr-layout-paddle`, con `paddleocr`/`paddlepaddle` solo en su imagen y perfil Compose `lab`; convierte imágenes a `numpy.ndarray` y extrae tax lines, tablas, multi-columna, label/value y orden de lectura. 6 tests de comportamiento pasan y `/health` real responde. El modo por defecto `PADDLE_PIPELINE=ocr` usa modelos `PP-OCRv5_mobile` configurables para CPU; `structure` queda reservado a una imagen de benchmark con `PADDLE_INSTALL_STRUCTURE=1`. La imagen actual se reconstruyó, la caché de modelos es persistente, el inicializador corrige permisos sin elevar el servidor y el smoke real `/layout` devuelve evidencia sobre una factura en 27-35 s usando menos de 1 GiB. Falta el benchmark completo contra ground truth y decidir si la precisión compensa la latencia. |
| R-042 | VERIFYING | R-032 | `SuryaLayoutEngine` y endpoint `/layout` viven en `services/ocr-layout-surya`, con `surya-ocr` solo en su imagen y perfil Compose `lab`; usa el mismo contrato y evidencia comparable. 5 tests de comportamiento pasan, la imagen CPU se construye y `llama-server` arranca; el endpoint completo no cumple un p95 aceptable en CPU (más de 5 minutos y generación aproximada de 8 s/token), por decisión explícita queda bloqueado como challenger hasta disponer de GPU o backend externo. |
| R-043 | VERIFYING | R-033 | Colas `ocr:primary` y `ocr:background`, encolado de usuario separado de comparativa/benchmark y `BackgroundWorkerSettings`; smoke real de ARQ contra Redis del stack (`REDIS_URL=redis://172.19.0.9:6379/15`) pasa. Falta validación de recuperación en staging. |
| R-044 | VERIFYING | R-043 | `ocr_worker_max_jobs=4` y `ocr_background_worker_max_jobs=1` cableados a workers primario/background. `test_worker_limits.py` y el smoke de wiring pasan. Falta calibración con carga real. |
| R-045 | VERIFYING | R-034,R-043 | Máquina de estados `closed/open/half_open` con ventana, cooldown y probe distribuido único mediante `SET NX` con TTL por `engine:model`, conectada al intento primario del worker con degradación segura si Redis no está disponible. 3 tests pasan y smoke real contra Redis confirma que dos workers no toman el mismo probe; falta validar outage completo en staging. |
| R-046 | VERIFYING | R-033,R-043 | Migración `0050_r046_ocr_lab_settings`, controles de laboratorio separados (`lab_visible`, benchmark automático, motores y variantes), endpoint admin-tech, botón de apagado sin llamadas automáticas, promoción explícita con confirmación y registro append-only de política anterior/nueva, actor y fecha. `test_platform_settings.py`: 9 passed; `PlatformSettings.test.tsx`: 3 passed; queda validación completa de staging. |
| R-047 | VERIFYING | R-016,R-020 | Telemetría Prometheus sin PII: subida aceptada, espera/procesamiento OCR, fallback y fallo, guardado de borrador, duración de revisión y contadores pending/ready/expired. Etiquetas limitadas a motor, modelo, estado y bucket de páginas; 161 tests puros pasan; integración requiere Redis/Postgres. |
| R-048 | VERIFYING | R-047 | ETA aproximada por combinación motor/modelo/bucket de páginas, con muestras agregadas de 30 días y mínimo de 30 completadas. Usa concurrencia efectiva y devuelve rango, nunca precisión falsa; sin base suficiente devuelve `null`. La migración `0055_r048_eta_definer_grants` corrige los permisos del `SECURITY DEFINER`; la función registra muestras correctamente en Postgres real y la factura real reprocesada terminó en `needs_review`. El nuevo test HTTP persiste 30 muestras y verifica que `GET /uploads/{id}/status` devuelve `25-30 s`; R-016/R-017 + ETA pasan `7 tests`. Falta verificación visual completa en UI y staging. |
| R-049 | VERIFYING | R-020,R-021,R-027 | Owner guard separado para edición, supervisión explícitamente read-only, admin-tech sin camino de escritura de facturas y `Cache-Control: private, no-store, max-age=0` + `Pragma: no-cache` globales. 5 tests de aislamiento HTTP y 9 regresiones de autorización/cabeceras/ETA pasan contra servicios reales; falta repetir el escenario de staging completo. |
| R-050 | VERIFYING | R-043,R-047 | Arnés `backend/scripts/r050_load_test.py` para 10×10 uploads, polling OCR, p50/p95, 429, métricas de pool/Redis, línea base y delta de recuperación (`pending/processing/abandoned/failed/expired`) y comprobación de fugas entre bandejas. Tenant efímero aislado con extractor `APP_ENV=load_test`: las corridas válidas dieron 100/100 `201`, cero fugas y cero `429`; la mejor medición reproducible quedó en p95 `3.26 s`. La coordinación single-flight de MinIO, el CTE atómico de auditoría y la migración `0056_r050_ctx` están verificadas; `28` contratos de intake y `23` gates focalizados pasan contra servicios reales. Por decisión de Julio, el p95 estricto de 3 segundos no bloquea: se acepta un flujo completo del orden de 8-10 segundos siempre que conserve aislamiento, integridad y recuperación. Falta solo la verificación completa de staging para cerrar R-050. Evidencia persistida en `docs/evidence/load/`. |
| R-051 | VERIFYING | R-049,R-050 | Flags cerrados en configuración con allowlist de tenants, defaults compatibles y rollback sin downgrade. Los siete flags tienen consumidor o fallback explícito, incluido scanner legacy y política OCR legacy. `docs/runbooks/r051-rollout-and-rollback.md` y `docs/runbooks/rollback.md` documentan rollback funcional, de versión, de migración y restore. El canario técnico está activo para Setex y las pruebas funcionales reales pasaron con `soporte@autoken.es`: subida, OCR, revisión y confirmación de facturas emitidas sin perder datos. La nueva prueba manual del 27/08 recibió `201`, terminó OCR en unos 12 s, quedó en `needs_review` y terminó `confirmed`. El despliegue oficial con `infrastructure/deploy.sh` quedó verificado hoy: API/worker en perfil `proxy`, red y routers Traefik presentes, y health JSON `200` en `panel-staging.autoken.es` y `setex.autoken.es`; el preflight devuelve `ready: true`. La simulación de rollback cubre los siete flags y pasa `12 tests`; el rollback real de `SUPPLIER_LEARNING_ENABLED` se aplicó y restauró con health/preflight correctos, sin migraciones ni borrado de datos. Sigue en `VERIFYING` por la validación completa de staging y el canario/rollback final. |
| R-052 | VERIFYING | R-020,R-022,R-024,R-025,R-049 | Spec aprobada el 27/08. La confirmación deja de navegar automáticamente y muestra decisión Sí/No; las facturas no confirmadas se pueden eliminar con borrado DB-first, cascada de borrador/páginas y limpieza MinIO post-commit; las confirmadas devuelven 409. Deduplicación por SHA-256 conserva revisión de la original/repetición; duplicación por número+CIF propio+CIF contraparte e importe bloquea review/confirm. Se añadieron marcas locales de rendimiento para frame, análisis, procesamiento y preview, y precalentamiento de OpenCV al abrir cámara. Si falla el análisis OpenCV, se conserva el frame completo y la vista previa no se bloquea (C14, test de comportamiento). Frontend: 446 tests, typecheck, build y lint correctos. Backend: ruff, mypy, compileall y 6 tests R-052 (3 HTTP y 3 puros) pasan contra el stack Docker con fixtures efímeros. El hotfix se ha desplegado en staging y el health público sigue correcto. No requiere migración. Pendiente de validación manual de UX en navegador y de medir el flujo en PC real. |
| R-053 | VERIFYING | R-049,R-052 | Spec aprobada el 27/08. Se aplica únicamente una paleta crema/clara desde tokens compartidos: contenido autenticado, captura fuera de cámara, panel tenant y panel tech-admin. La barra superior permanece oscura y la superficie de cámara conserva fondo oscuro y texto claro. Se preservan theming dinámico, permisos, estructura, textos, botones y funcionalidades. Frontend: 446 tests, typecheck, build y lint correctos; despliegue staging verificado. Pendiente de revisión visual manual en todos los roles/pantallas. |
| R-054 | VERIFYING | R-053 | Spec aprobada el 28/08. Implementado el sistema visual Tinted Navy Liquid Glass: shell claro con fondo atmosférico, tokens compartidos, navegación superior glass, acciones con acabado naranja glass, modales glass, captura/preview, bandeja, historial y paneles tenant/platform con superficies sólidas. En captura, `Tomar foto` y `Subir archivo` comparten fila y altura; `Varias facturas`/`Varias hojas` tienen iconos; dirección usa toggle segmentado con `Recibida` por defecto. La cámara conserva fondo oscuro y se mantienen fallback sin blur, reduced motion, forced colors y foco visible. No se han tocado lógica, rutas, permisos, contratos ni textos funcionales. Frontend: 446 tests, typecheck, build y lint correctos; desplegado y verificado en staging; pendiente revisión visual manual responsive y por rol. |

## Evidencia frontend transversal

- `frontend/src/shared/Modal.tsx` centraliza los diálogos con nombre accesible, foco inicial, ciclo de foco con `Tab`, cierre con `Escape`, cierre por fondo y restauración del foco anterior.
- `InvoiceImageModal`, `TaxLinesModal`, `ExamplesModal` y `ConfirmDeleteCompaniesDialog` reutilizan el modal común sin cambiar sus contratos de negocio ni sus acciones.
- `frontend/src/index.css` define valores iniciales de los tokens de branding; `tailwind.config.js` conecta `emerald-600` al color primario dinámico del tenant y expone tokens `brand-primary`/`brand-secondary`.
- `frontend/src/shared/Modal.test.tsx` cubre el comportamiento observable de accesibilidad y cierre; el nombre accesible histórico del diálogo de borrado conserva sus regresiones existentes.
- `frontend/src/index.css` contiene los tokens R-054, el tratamiento Tinted Navy Liquid Glass, superficies sólidas para datos, fallback sin `backdrop-filter` y ajustes para reduced motion, contraste aumentado y forced colors. Las clases visuales se aplican sobre el app-shell existente sin modificar sus contratos.
- `npm test`: 446 tests pasando; `npm run typecheck`; `npm run build`; `npm run lint` sin errores y con solo los 2 warnings preexistentes de `SessionProvider`. El hotfix está desplegado en staging.

## Evidencia R-006/R-007

- `frontend/src/features/capture/qualitySignals.ts` obtiene las señales de exposición, clipping y perspectiva de cada frame; la nitidez de `analyzeFrame.ts` se calcula sobre el área delimitada por las esquinas detectadas.
- `frontend/src/features/capture/stability.ts` exige estabilidad temporal, número mínimo de frames, movimiento máximo de esquinas y variación máxima de área antes de armar AUTO.
- `frontend/src/features/capture/useAutoCapture.ts` conecta análisis, quality gate, temporizador de confirmación y reducer; si falta cualquier señal real, AUTO no se arma.
- `frontend/src/features/capture/CaptureScreen.tsx` ofrece AUTO por defecto y MANUAL como alternativa, manteniendo el disparo consciente y el lock único de captura.
- `npm test -- --pool=threads --maxWorkers=1`: 441 tests pasando; `npm run typecheck`; `npm run build`; lint sin errores y con solo 2 warnings previos.

## Evidencia R-009

- `frontend/src/features/capture/processCapture.ts` no recorta ni endereza cuando las esquinas están fuera de imagen, dentro de la banda de clipping, no forman un área suficiente, son degeneradas o presentan perspectiva extrema.
- `frontend/src/features/capture/analyzeFrame.ts` usa `OffscreenCanvas` cuando está disponible y cae al canvas del navegador solo fuera de worker; el análisis sigue separado del still HD.
- `frontend/src/features/capture/processCapture.test.ts`: 8 casos de geometría fiable/no fiable y fallback ante fallos de OpenCV; `qualityGate.test.ts` añade 6 casos de señales `NaN`/`Infinity`.

## Evidencia de R-016/R-017

- `backend/migrations/versions/0041_processing_stage.py` añade las columnas, constraint y permisos mínimos.
- `backend/src/invoice_intake/repository.py` mantiene el fencing en claim, cambio de etapa, cierre y reintento.
- `backend/src/jobs/ocr.py` escribe solo etapas reales y termina con etapa nula y timestamp final.
- `backend/tests/test_s6_16_processing_stage.py` cubre flujo normal y worker antiguo.
- `backend/src/invoice_intake/router.py` publica el status privado sin CIF, raw OCR ni ubicación de MinIO.
- `frontend/src/features/processing/` contiene el modelo y la barra accesible, incluyendo fallback indeterminado para backends antiguos.
- `frontend/openapi.json` y `frontend/src/api/schema.d.ts` se regeneraron desde FastAPI.
- `pytest -q tests/test_s6_16_processing_stage.py`: 3 passed.
- `pytest -q tests/test_s6_16_processing_stage.py tests/test_intake_download.py tests/test_s6_13_recoverable_ocr.py`: 21 passed.
- `npm run test`: 357 passed; `npm run typecheck`; `npm run build`.
- `mypy src`, `ruff check src tests` y `ruff format --check src tests`: verdes.

## Evidencia de R-020

- `backend/src/invoicing/repository.py` lista únicamente los uploads propios, excluye facturas de prueba y ordena por `(created_at DESC, id DESC)`.
- `backend/src/invoicing/service.py` codifica el cursor sin datos fiscales y mantiene `SELF ONLY` también para `tenant_admin`.
- `backend/src/invoicing/router.py` publica `GET /api/v1/invoices/inbox` con DTO sin CIF, proveedor, número, importes ni OCR raw.
- `frontend/src/features/inbox/` contiene la bandeja, carga incremental y una sola consulta agregada con polling de 2 segundos mientras hay procesamiento.
- `frontend/openapi.json` y `frontend/src/api/schema.d.ts` se regeneraron desde FastAPI.
- `pytest -q tests/test_invoice_inbox.py tests/test_s6_16_processing_stage.py`: 7 passed.
- `npm run test -- --run src/features/inbox/InvoiceInbox.test.tsx`: 2 passed.
- `mypy src`, Ruff backend, `npm run typecheck` y `npm run lint`: verdes; lint frontend mantiene un warning preexistente en `SessionProvider.tsx`.

## Evidencia de R-021/R-022

- `backend/migrations/versions/0042_review_drafts.py` crea la tabla separada de `invoices`, con RLS FORCE por tenant/empresa y grants mínimos de la aplicación.
- `backend/src/invoicing/draft_repository.py` cifra CIF/nombre con `pgp_sym_encrypt`, calcula el índice ciego y actualiza usando revisión optimista.
- `backend/src/invoicing/draft_service.py` autoriza el fichero antes de guardar y devuelve conflictos sin sobrescribir el último snapshot.
- `backend/src/invoicing/router.py` publica `PUT /api/v1/uploads/{file_id}/draft` con el contrato de la especificación.
- `frontend/src/features/confirmation/useReviewDraft.ts` y `useDraftAutosave.ts` guardan el formulario tras 750 ms y permiten un guardado final antes de confirmar.
- `frontend/openapi.json` y `frontend/src/api/schema.d.ts` se regeneraron después de añadir el endpoint.
- `pytest -q tests/test_invoice_drafts.py tests/test_invoice_inbox.py tests/test_s6_16_processing_stage.py tests/test_invoice_history.py`: 12 passed.
- `npm run test -- --run`: 361 passed; `npm run typecheck`; `npm run build`.

## Evidencia de R-023

- `backend/src/invoicing/draft_repository.py` lee y descifra el borrador dentro del contexto RLS.
- `backend/src/invoicing/service.py` usa los campos del borrador cuando existe, recalcula veredicto y cuadre con esos valores y conserva las confianzas originales del OCR.
- `backend/src/invoicing/router.py` añade `source`, `draft_revision`, `draft_updated_at` y `page_count` a la respuesta de review.
- `frontend/src/features/confirmation/types.ts` consume la metadata y conserva la revisión al continuar el autosave.
- `pytest -q tests/test_invoice_confirm.py`: 26 passed.
- Ruff y mypy backend, typecheck y lint frontend: verdes; permanece el warning preexistente de `SessionProvider.tsx`.

## Evidencia de R-024

- `backend/src/invoicing/service.py` revalida y confirma los valores del borrador, ignorando un body obsoleto del cliente.
- `backend/src/invoicing/draft_repository.py` elimina `review_drafts` después de la transición a `confirmed`, usando la misma sesión transaccional.
- Una guarda fallida conserva el borrador y una confirmación correcta lo elimina después de persistir la factura.
- `pytest -q tests/test_invoice_confirm.py tests/test_invoice_drafts.py`: 31 passed.
- No se ejecuta ningún cleanup de MinIO durante la confirmación.

## Evidencia de R-025

- `frontend/src/features/confirmation/postConfirmNavigation.ts` invalida la cache de inbox y solicita un snapshot nuevo solo después del éxito de confirmación.
- La selección ignora el documento recién confirmado y solo considera `ocr_done`/`needs_review` como siguientes revisables.
- Si no hay siguiente documento o falla la consulta, navega a `/mis-facturas`.
- `frontend/src/app/AppRoutes.tsx` conecta esta navegación al callback de éxito del confirm.
- `npm run test -- --run`: 364 passed; `npm run typecheck`; lint mantiene solo el warning preexistente de `SessionProvider.tsx`.

## Evidencia de R-026

- `backend/src/invoicing/repository.py` lista solo uploads no confirmados de otros usuarios, con empresa, usuario, estado, fecha, dirección y páginas.
- `backend/src/invoicing/router.py` publica `GET /api/v1/invoices/pending-supervision` y `GET /api/v1/uploads/{file_id}/review-readonly` como puertas separadas del flujo editable.
- `frontend/src/features/supervision/` contiene el listado paginado y la pantalla de apertura read-only, sin autosave, guardar, confirmar ni confirmar-siguiente.
- `frontend/src/app/routes.ts` y `AppRoutes.tsx` registran `/pendientes-equipo` solo para `tenant_admin`.
- `pytest -q tests/test_invoice_supervision.py tests/test_invoice_inbox.py tests/test_invoice_confirm.py`: 34 passed.
- `npm run test -- --run`: 366 passed; OpenAPI regenerado; head Alembic `0042_review_drafts`.

## Evidencia de R-049 (avance)

- `invoice_intake.authorize_file_edit` separa lectura de escritura y aplica owner guard al
  `tenant_admin`; protege borrador, review, confirmación, verificación de contraparte y reintento OCR.
- `GET /uploads/{file_id}/review-readonly` y la apertura admin-tech usan explícitamente el camino de
  solo lectura, sin reutilizar una autorización editable.
- Las respuestas de la API llevan `Cache-Control: private, no-store, max-age=0` y `Pragma: no-cache`;
  logout ya limpia la caché de TanStack Query y las vistas revocan las blob URLs.
- `pytest -q tests/test_intake_authorization.py tests/test_security_headers.py tests/test_ocr_eta.py`:
  9 passed.
- `npm run test -- --run`: 367 passed; `npm run typecheck`; `npm run lint` con el warning preexistente de
  `SessionProvider.tsx`.
- `test_tenant_isolation.py`: 5 passed contra Postgres, Redis y MinIO reales del stack; el caso que
  antes estaba bloqueado por MinIO se repitió usando las credenciales del contenedor sin imprimirlas.
- `test_intake_authorization.py tests/test_security_headers.py tests/test_ocr_eta.py`: 9 passed.

## Evidencia de R-050 (avance)

- `backend/scripts/r050_load_test.py` ejecuta 100 uploads concurrentes de imágenes válidas distintas,
  espera estados OCR, obtiene snapshot Prometheus y comprueba `SELF ONLY` para los diez usuarios.
- `/api/v1/metrics` expone solo agregados de pool (`size`, `checked_out`, `overflow`, `capacity`),
  disponibilidad de la cola OCR y respuestas 429 del proveedor por motor/modelo; no expone
  credenciales, IDs de factura ni datos fiscales.
- `DB_POOL_SIZE` y `DB_MAX_OVERFLOW` quedan documentados en `.env.example` y cableados en Compose.
- `docs/runbooks/r050-load-and-recovery.md` documenta carga, rate-limit, caída/recuperación de Redis,
  proveedor `429` y evidencia sin PII.
- `pytest -q tests/test_r050_load_test.py tests/test_security_headers.py tests/test_ocr_eta.py`:
  9 passed en la verificación focalizada previa; Ruff y mypy pasan.
- `pytest -q tests/test_r050_load_test.py`: 4 passed después de añadir la comparación con la línea base
  global de recuperación.
- El ensayo real del 26/08/2026 se ejecutó con tenant efímero, diez usuarios sintéticos, MinIO, ClamAV,
  Redis DB `/15`, API y worker separados, sin Gemini ni Setex: 100 respuestas `201`, p50 `3.68 s`,
  p95 `4.44 s`, 100 `needs_review`, 0 `429` y `cross_user_leaks=0`.
- La interrupción controlada del 26/08/2026 se repitió con una cola Redis exclusiva: 8 uploads recibieron
  `201` antes de la caída y 92 recibieron `500` durante la indisponibilidad. Postgres conservó los 8
  documentos aceptados, con 7 procesados y 1 `pending_ocr`; después de limpiar únicamente Redis DB `/15`,
  `recover_ocr_documents()` observó `pending=1`, reencoló 1 trabajo y el worker dejó los 8 documentos en
  `needs_review`. Todas las extracciones fueron `load-test/deterministic`; no hubo llamada a Gemini.
- Para el camino caliente se eliminó el `HEAD bucket_exists` repetido por upload, con invalidación y
  reintento seguro si MinIO confirma un bucket borrado, se agruparon los dos contadores Redis del
  rate-limit en un único `EVAL` atómico de dos claves y se fusionaron los dos `set_config` de RLS en una
  sola sentencia cuando aplica. El dependency de upload resuelve solo el id de empresa, sin descifrar
  el nombre que necesita `/auth/me`. La repetición final válida obtuvo p95 `3.26 s`, la mejor medición
  reproducible hasta ahora, pero todavía no demuestra el objetivo `<=3 s`.
- Se midieron los planes SQL del camino de deduplicación contra Postgres real: las restricciones únicas
  `(company_id, uploaded_by, sha256)` de raíz y páginas están disponibles; la ejecución observada fue
  `0.03 ms` para la raíz y `0.09 ms` para la consulta combinada. No se añade un índice ni una reescritura
  especulativa: el margen restante del p95 no está en el plan SQL medido.
- La métrica global ya tenía un `ocr_failed=1` de otro tenant creado el 29/07. El informe conserva la
  línea base y el delta; durante el ensayo el delta de `failed` fue `0` y el tenant sintético no tuvo
  fallos.
- Se corrigió `r050_provision.py` para borrar primero `uploaded_files` y después usuarios/tenant. El
  cleanup se verificó dos veces contra el Postgres real y no quedaron contenedores ni tenant de carga.
- La repetición aislada posterior a la coordinación single-flight obtuvo `100/100` respuestas `201`,
  `100 needs_review`, `0` `429`, `cross_user_leaks=0` y p95 `4,52 s`. Confirma funcionalidad y aislamiento,
  pero no cumple el SLO; no se sustituye la mejor evidencia anterior de `3,26 s`.
- Se añadió `autoken_upload_phase_seconds`, con fases cerradas y sin etiquetas de tenant o factura, para
  localizar el coste del camino caliente. La oleada diagnóstica del 26/08/2026 obtuvo `100/100` `201` y
  p95 `5,01 s`: los mayores tiempos agregados fueron deduplicación (`57,61 s`) y persistencia (`53,83 s`);
  ClamAV (`8,38 s`) y MinIO (`8,38 s`) no explican por sí solos el p95. El informe queda separado como
  diagnóstico porque el tenant no estaba en el allowlist de la bandeja (`inbox_http_errors=10`), sin
  atribuir esos `404` a fugas. Evidencia en `docs/evidence/load/r050-phase-diagnostic-2026-08-26.json`.
- La fase `identity` también mide la resolución fresca de empresa en la dependencia de upload. Con el
  tenant efímero incluido en el allowlist, la nueva corrida obtuvo `100/100` `201`, p50 `3,65 s`, p95
  `3,94 s`, `cross_user_leaks=0` e `inbox_http_errors=0`; `identity` sumó `41,61 s`, deduplicación
  `43,82 s` y persistencia `46,22 s`. No se añade caché porque la spec exige resolver la pertenencia
  por petición. Evidencia en `docs/evidence/load/r050-identity-phase-diagnostic-2026-08-26.json`.
- El ensayo comparativo `DB_POOL_SIZE=30`/`DB_MAX_OVERFLOW=0` aceptó las subidas, pero agotó el pool durante
  el polling y produjo `QueuePool timeout`; queda descartado como ajuste de cierre para R-050. El pool
  configurable debe conservar overflow suficiente para el pico y para las lecturas concurrentes.
- `DB_POOL_PRE_PING` queda explícito y configurable, con `true` por defecto. Desactivarlo en un ensayo
  aislado solo redujo el p95 de `3,94 s` a `3,86 s`, todavía fuera del SLO, y elimina la protección contra
  conexiones muertas; no se adopta como configuración de staging/producción.
- La métrica `autoken_db_session_setup_seconds{phase=...}` separa adquisición/configuración RLS de la
  consulta. La última oleada obtuvo `100/100` `201`, p50 `3,62 s`, p95 `3,85 s`, cero fugas y cero errores
  de bandeja; la preparación de sesión sumó `24,83 s` en identidad, `33,05 s` en deduplicación y `22,32 s`
  en persistencia. La evidencia queda en `docs/evidence/load/r050-session-setup-diagnostic-2026-08-26.json`.
- La siguiente optimización debe reducir round-trips o repartir explícitamente el pool por proceso/worker;
  no se cambia el tamaño global sin verificar `max_connections` para API, worker y réplicas.
- La comparación reproducible de pool (`20/20`, `30/0`, `40/20`) confirma que aumentar capacidad no cierra
  el SLO: `30/0` agota conexiones durante el polling y `40/20` empeora el p95 a `4,86 s`. Se conserva
  `20/20`; evidencia en `docs/evidence/load/r050-pool-comparison-2026-08-26.json`.
- La persistencia del upload simple fusiona ahora el `INSERT` de `uploaded_files` y el de `audit_log` en
  un CTE SQL atómico. La corrida de validación mantuvo `100/100` `201`, cero fugas y bajó la suma de
  persistencia a `38,40 s`, pero obtuvo p95 `4,06 s`; es una optimización válida, no el cierre del SLO.
  Evidencia en `docs/evidence/load/r050-cte-audit-2026-08-26.json`.
- La nueva corrida aislada del 27/08/2026 aceptó `100/100` uploads con p50 `3,59 s` y p95 `3,97 s`.
  Los 100 documentos terminaron en estados terminales (`93 needs_review`, `7 capture_unreadable`), con
  `cross_user_leaks=0`, `inbox_http_errors=0` y `0` respuestas `429`. El tenant efímero, sus objetos y
  usuarios fueron eliminados después. Evidencia en `docs/evidence/load/r050-isolated-2026-08-27.json`.
- La recuperación aislada usó una Redis efímera separada: durante 100 intentos hubo `69` respuestas `201`
  y `31` `500` durante la ventana de caída, sin errores de transporte. Tras restaurar Redis y ejecutar el
  recuperador, los 69 documentos aceptados terminaron sin pendientes ni fallidos (`53 capture_unreadable`,
  `16 needs_review`). Evidencia en `docs/evidence/load/r050-recovery-isolated-2026-08-27.json`.
- El escenario controlado de proveedor limitado pasa `2 tests`: un `429` del primario activa el fallback,
  la factura termina en `ocr_done`, aumenta en uno la métrica `autoken_ocr_provider_429_total` y el mensaje
  del proveedor no aparece en la extracción persistida; además, el adaptador Gemini conserva la
  clasificación cuando el SDK solo expone `status_code=429`. Evidencia en
  `docs/evidence/load/r050-provider-429-2026-08-27.json`.

## Evidencia de R-048 (avance)

- `ocr.eta.estimate_eta` no devuelve ETA con menos de 30 muestras y calcula el rango con p75 y
  concurrencia efectiva cuando alcanza el mínimo.
- `test_status_endpoint_muestra_eta_solo_con_muestras_suficientes` inserta 30 muestras sintéticas en
  Postgres, consulta el endpoint HTTP de estado bajo RLS y verifica el rango `25-30 s`, sin exponer PII.
- `pytest -q tests/test_s6_16_processing_stage.py tests/test_ocr_eta.py`: `7 passed` contra Postgres,
  Redis y MinIO reales del stack.

## Evidencia de staging y despliegue (avance)

- `HEALTHCHECK_HOSTS=panel-staging.autoken.es,setex.autoken.es bash infrastructure/deploy.sh` reconstruye
  las imágenes y verifica API, frontend, worker, red `proxy`, routers Traefik y health público.
- El preflight de R-051 ejecutado dentro de la imagen desplegable devuelve `ready: true`: 7 flags válidos,
  1 tenant piloto y variables secretas requeridas presentes, sin imprimir valores.
- `panel-staging.autoken.es/api/v1/health` y `setex.autoken.es/api/v1/health` responden `200` JSON desde
  FastAPI, con `server: uvicorn`, `Cache-Control: private, no-store` y cabeceras de seguridad.
- La regresión combinada de R-016/R-017/R-048/R-049/R-050/R-051 pasa `28 tests` contra Postgres, Redis,
  MinIO y el stack desplegado.

## Auditoría de prerrequisitos de go-live (avance)

- `docker compose --env-file .env -f infrastructure/docker-compose.yml -f infrastructure/docker-compose.prod.yml
  --profile tools run --rm --entrypoint alembic migrate current` confirma `0056_r050_ctx (head)` usando
  el rol administrador. El intento equivalente dentro de API fue rechazado por permisos, como debe ser para
  `autoken_app`; el runbook queda validado con el servicio `migrate`.
- El backup cifrado nocturno del `2026-08-27` se generó en `0,62 s`, con `373833` bytes, se subió al servidor
  externo `72.62.189.27` y no expuso secretos en el log. El restore drill ya estaba validado previamente.
- El stack público continúa en `APP_ENV=staging`, `DEPLOYMENT_PROFILE=proxy`, con API/worker sanos y health
  JSON `200` en `panel-staging.autoken.es` y `setex.autoken.es`.
- Los bloqueos restantes son externos al código: aprobación/tag de release `v2.0.0`, elección de ventana
  nocturna para la migración de Setex, inventario/validación uno a uno de las 51 empresas y 4 facturas, DNS
  definitivo y confirmación de credenciales SMTP. No se inventa ninguno ni se ejecuta una migración real sin
  esos datos.

## Evidencia del canario manual (avance)

- El 27/08/2026 se hizo una subida manual nueva desde `setex.autoken.es` con la cuenta de soporte y la
  empresa asignada. La API respondió `201`, el worker ejecutó OCR real y terminó en `needs_review` tras
  aproximadamente 12 segundos.
- La revisión humana se guardó y la confirmación respondió correctamente; Postgres muestra el documento
  final en estado `confirmed`. No se registró un fallo OCR ni se imprimieron datos de la factura.

## Evidencia de R-051 (avance)

- `shared.rollout.FeatureFlag` mantiene una allowlist cerrada de siete flags; un flag apagado siempre
  gana y una allowlist no vacía limita el flag al tenant piloto.
- `Settings` conserva por defecto el comportamiento actual y acepta `ROLLOUT_TENANT_ALLOWLIST` sin
  exponerla a clientes.
- `supplier_learning_enabled=false` evita actualizar perfiles agregados sin impedir confirmar facturas.
- `GET /auth/me` devuelve únicamente los flags ya evaluados para el tenant; nunca devuelve la allowlist
  ni la configuración de despliegue. `review_inbox_enabled` y `draft_autosave_enabled` ya tienen gate
  tanto en API como en frontend; desactivarlos no bloquea la confirmación manual.
- `scanner_v2_enabled=false` conserva la captura original sin análisis ni recorte OpenCV.
- `ocr_policy_v2_enabled=false` conserva el primario legacy Gemini 3 Flash, sin fallback ni consulta a
  la política persistida.
- `backend/scripts/r051_canary_preflight.py` valida los siete flags, la allowlist y los secretos mínimos
  de staging sin imprimir valores sensibles; tres tests de comportamiento pasan.
- `tests/test_ocr_policy.py` cubre la selección legacy sin consultar Postgres; junto con los tests de
  flags, fallback, consenso, carga, cabeceras y ETA: 21 tests pasan.
- `docs/runbooks/r051-rollout-and-rollback.md` documenta el orden CI/local/staging/canario/25%/100%,
  la configuración y el rollback sin downgrade.
- `pytest -q tests/test_rollout_flags.py`: 5 passed; mypy y Ruff dirigidos pasan. Frontend completo:
  370 tests passed, typecheck y build correctos; lint sin errores (mantiene dos warnings existentes de
  Fast Refresh en `SessionProvider.tsx`).
- El canario técnico quedó activado únicamente para Setex: preflight `ready: true`, los siete flags activos
  para su UUID y todos apagados para Paddle-lab. API y worker cargaron la configuración sin exponer la
  allowlist; health y `/api/v1/metrics` respondieron `200`.
- `test_rollout_flags.py`: `12 passed`, incluyendo una regresión para cada uno de los siete flags que
  verifica que `false` gana sobre una allowlist que contiene el tenant piloto. El staging real no se
  modificó durante esta simulación.
- Rollback real del 27/08: `SUPPLIER_LEARNING_ENABLED` pasó temporalmente a `false`; API y worker cargaron
  el valor, los otros flags y la allowlist quedaron iguales, preflight siguió en `ready: true` y ambos
  health públicos respondieron `200`. Se restauró a `true` con el mismo resultado. Evidencia en
  `docs/evidence/load/r051-rollback-supplier-learning-2026-08-27.json`.
- La base de datos estaba en `0040_ocr_irpf_fields`; se aplicaron transaccionalmente las migraciones `0041`
  a `0054` y Alembic quedó en `0054_r013_capture_session (head)`. Las pruebas focalizadas de flags y
  preflight pasan: 9 tests. Sigue pendiente la ejecución manual de una factura real de Setex.
- El incidente de Traefik se cerró de forma permanente: `Settings` rechaza `staging/production` con
  `DEPLOYMENT_PROFILE=standalone`; el overlay fija `proxy` para API/worker y `infrastructure/deploy.sh`
  reconstruye, espera healthchecks, verifica red/labels y comprueba el health público. La causa, decisión
  y procedimiento están en `docs/adr/0020-despliegue-publico-con-overlay-proxy.md` y los runbooks.

## Evidencia de aislamiento de suites

- `tests._dbtest._worker_suffix` añade un sufijo aleatorio a cada base efímera. Esto evita que dos
  contenedores Docker con el mismo PID interno compartan `autoken_test_*` y se desconecten mutuamente.
- La regresión `tests/test_dbtest_naming.py` pasa en sus dos variantes, con y sin `pytest-xdist`.
- El Redis de test continúa siendo un recurso compartido en la base `/15`; no se debe ejecutar en paralelo
  sin separar también ese namespace, porque el fixture usa `flushdb()` por caso.

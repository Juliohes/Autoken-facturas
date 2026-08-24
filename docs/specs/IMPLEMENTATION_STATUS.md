# Estado de Implementación de la Especificación Maestra

Registro operativo de `ESPECIFICACION_MAESTRA_AUTOKEN_AUTOFACTU_PRODUCCION_v3.md`.
Un requisito solo pasa a `DONE` con implementación y evidencia verificable.

| ID | Estado | Dependencias | Evidencia / observaciones |
|---|---|---|---|
| R-000 | IN_PROGRESS | — | `alembic heads` devuelve un único head (`0040` antes del cambio); `alembic current` quedó bloqueado por resolución DNS del entorno real. |
| R-001 | VERIFYING | R-000 | Precedencia recogida en la especificación y la captura existente; falta reconciliación formal. |
| R-002 | VERIFYING | R-001 | La pantalla ofrece factura simple, varias facturas y una factura multipágina; el contrato de captura continua comprueba 3 `file_id` independientes y el flujo multipágina conserva 1 raíz. Falta validación E2E real en dispositivo. |
| R-003 | VERIFYING | R-001 | Tipos de captura existentes; falta auditoría contra la taxonomía maestra. |
| R-004 | VERIFYING | R-003 | `scanner.worker.ts`, `scannerProtocol.ts` y `useScannerEngine.ts`; máximo un análisis en vuelo, descarte de frames ocupados y guardia de resultados obsoletos. Test de comportamiento, suite frontend y build pasan; falta validación en navegador/dispositivo real. |
| R-005 | VERIFYING | R-003 | Detector OpenCV con scoring de área, rectangularidad, convexidad, centrado, continuidad, margen y aspecto; prior de confianza por método. 9 tests OpenCV pasan; falta validación con imágenes reales de dispositivo. |
| R-006 | VERIFYING | R-005 | `qualityGate.ts` puro con razones explícitas para documento, confianza, tamaño, clipping, nitidez, exposición, perspectiva y estabilidad. 10 tests de comportamiento pasan. |
| R-007 | VERIFYING | R-006 | Máquina `AUTO/MANUAL` y lock compartido en `captureLoop.ts`; el lock también protege la captura manual real. 3 tests R-007 pasan; falta cerrar la UI completa de cambio de modo. |
| R-008 | VERIFYING | R-005 | `coordinates.ts` compensa explícitamente `object-cover`; `DocumentOverlay.tsx` dibuja guía y polígono SVG con estados. 3 tests de coordenadas, suite frontend y build pasan; falta validación visual en navegador/dispositivo real. |
| R-009 | VERIFYING | R-005,R-007 | `grabVideoFrame.ts` prioriza `ImageCapture.takePhoto()` con fallback canvas; `analyzeFrame.ts` limita la copia de análisis a 1600 px y escala las esquinas al still original para redetección y warp. 3 tests R-009, suite frontend y build pasan; falta validación en dispositivo real. |
| R-010 | VERIFYING | R-009 | `CapturePreview.tsx` obliga a revisar la captura individual antes del POST, con `Repetir`, `Usar foto`, estados de guardado y limpieza de Blob URL. 3 tests de preview y suite frontend pasan; falta validación visual en dispositivo real. |
| R-011 | VERIFYING | R-010 | Frontend acepta solo `201` con `id` en `readUploadResult`, conserva el `409 duplicate_of`; backend declara `201`, deja `pending_ocr` y encola tras commit. 5 tests de contrato frontend y 405 tests frontend pasan; tests backend requieren Redis local/staging. |
| R-012 | VERIFYING | R-002,R-011 | `continuousCapture.ts` mantiene sesión UX con máximo 10, secuencia y timestamp; cada `201` permite la siguiente subida individual y los duplicados no se agregan dos veces. 4 tests puros y un escenario UI de 3 facturas pasan; falta E2E real con OCR concurrente y dispositivo. |
| R-013 | VERIFYING | R-012 | Migración `0054_r013_capture_session` añade `capture_session_id`, `capture_sequence`, constraint e índice parcial; ORM, `POST /uploads`, query ordenada por sesión y bandeja privada están alineados. El frontend envía UUID y secuencia; integración backend requiere Redis/Postgres. |
| R-014 | VERIFYING | R-011 | Flujo posterior a subida pendiente de validación contra el maestro. |
| R-015 | VERIFYING | R-011 | Retención del stream pendiente de validación contra el maestro. |
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
| R-041 | VERIFYING | R-032 | Contrato `DocumentLayoutEngine` y `LayoutEvidence` para challenger PaddleOCR en servicio de laboratorio, sin dependencia en el contenedor API. 1 test de contrato pasa; servicio concreto pendiente. |
| R-042 | VERIFYING | R-032 | El mismo contrato cubre challenger Surya y expone features de layout/orden de lectura para medir tax lines, tablas y columnas; 1 test de contrato pasa; servicio concreto pendiente. |
| R-043 | VERIFYING | R-033 | Colas `ocr:primary` y `ocr:background`, encolado de usuario separado de comparativa/benchmark y `BackgroundWorkerSettings`; falta validar runtime con Redis. |
| R-044 | VERIFYING | R-043 | `ocr_worker_max_jobs=4` y `ocr_background_worker_max_jobs=1` cableados a workers primario/background. 1 test pasa; runtime requiere Redis. |
| R-045 | VERIFYING | R-034,R-043 | Máquina de estados `closed/open/half_open` con ventana, cooldown, probe único y adaptador de estado Redis por `engine:model`, conectada al intento primario del worker con degradación segura si Redis no está disponible. 2 tests con reloj controlado pasan; runtime requiere Redis. |
| R-046 | VERIFYING | R-033,R-043 | Migración `0050_r046_ocr_lab_settings`, controles de laboratorio separados (`lab_visible`, benchmark automático, motores y variantes), endpoint admin-tech, botón de apagado sin llamadas automáticas, promoción explícita con confirmación y registro append-only de política anterior/nueva, actor y fecha. Tests frontend pasan; integración backend requiere Redis/Postgres. |
| R-047 | VERIFYING | R-016,R-020 | Telemetría Prometheus sin PII: subida aceptada, espera/procesamiento OCR, fallback y fallo, guardado de borrador, duración de revisión y contadores pending/ready/expired. Etiquetas limitadas a motor, modelo, estado y bucket de páginas; 161 tests puros pasan; integración requiere Redis/Postgres. |
| R-048 | VERIFYING | R-047 | ETA aproximada por combinación motor/modelo/bucket de páginas, con muestras agregadas de 30 días y mínimo de 30 completadas. Usa concurrencia efectiva y devuelve rango, nunca precisión falsa; sin base suficiente devuelve `null`. Disponible en estado privado del upload y visible como rango aproximado en la pantalla de procesamiento. Tests puros pasan; integración requiere Postgres. |
| R-049 | VERIFYING | R-020,R-021,R-027 | Owner guard separado para edición, supervisión explícitamente read-only, admin-tech sin camino de escritura de facturas y `Cache-Control: private, no-store, max-age=0` + `Pragma: no-cache` globales. 9 tests puros relacionados pasan; suite HTTP contra Postgres/Redis pendiente por servicios no disponibles. |
| R-050 | VERIFYING | R-043,R-047 | Arnés `backend/scripts/r050_load_test.py` para 10×10 uploads, polling OCR, p50/p95, 429, métricas de pool/Redis y comprobación de fugas entre bandejas. Pool configurable en Compose/.env. Runbook añadido; ejecución real pendiente de staging con Postgres/Redis/MinIO/worker. |
| R-051 | VERIFYING | R-049,R-050 | Flags cerrados en configuración con allowlist de tenants, defaults compatibles y rollback sin downgrade. Los siete flags tienen consumidor o fallback explícito, incluido scanner legacy y política OCR legacy; falta el canario real. |

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
- La prueba HTTP `tenant_admin` contra pendiente ajena está escrita, pero requiere Redis y Postgres
  reales; Redis no está disponible en `localhost:6379` en este entorno.

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
  9 passed; Ruff y mypy pasan.
- La ejecución de 100 uploads requiere staging con Postgres, Redis, MinIO, antivirus y worker OCR;
  no se ha declarado cierre empírico sin esos servicios.

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

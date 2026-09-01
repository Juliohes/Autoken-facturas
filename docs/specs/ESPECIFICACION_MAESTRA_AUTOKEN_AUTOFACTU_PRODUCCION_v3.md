
# ESPECIFICACIÓN MAESTRA DEFINITIVA — AUTOKEN FACTURAS / AUTOFACTU
## Escáner documental, captura continua, OCR asíncrono, progreso, bandeja privada, borradores, OCR adaptativo y aprendizaje por proveedor

> **Documento de implementación para LLM / agente de desarrollo**
>
> **Repositorio objetivo:** `Juliohes/Autoken-facturas`
>
> **Rama base auditada:** `develop`
>
> **Fecha de consolidación:** 2026-08-21
>
> **Estado:** especificación maestra de referencia para llevar App2 a producción con las mejoras consolidadas de App1 Setex, de las especificaciones previas aportadas y de patrones actuales del mercado.
>
> **Stack preservado:** React 18 + TypeScript + Vite + PWA + FastAPI + SQLAlchemy async + PostgreSQL + RLS + Redis + arq + MinIO + OpenCV.js + OCR/IA.
>
> **Principio rector:** **evolucionar la arquitectura actual; no construir un sistema paralelo**.

---

# 0. PROPÓSITO, ALCANCE Y REGLA DE PRECEDENCIA

Este documento consolida y sustituye, para este alcance concreto, las decisiones dispersas entre:

1. `ESPECIFICACION_ESCANER_DOCUMENTAL_AUTOKEN(1).md`.
2. `ESPECIFICACION_CAPTURA_CONTINUA_REVISION_BORRADORES_AUTOKEN_v2(1).md`.
3. El estado real auditado de `Juliohes/Autoken-facturas`, rama `develop`.
4. Las mejoras útiles detectadas en `Juliohes/Setex-facturas`, rama `main`.
5. La investigación de patrones actuales de productos/document-AI del mercado y herramientas open-source.

## 0.1. Precedencia ante contradicciones

La precedencia es:

```text
decisiones cerradas del documento de captura continua v2
>
estado de seguridad/multitenancy ya implantado en App2
>
este documento maestro
>
especificación anterior del escáner
>
ideas experimentales de Setex
>
patrones del mercado
```

### Conflicto ya resuelto: edición manual de esquinas

La especificación del escáner proponía `DocumentCropEditor` con handles arrastrables.

La especificación posterior de captura continua cierra expresamente lo contrario.

**Decisión definitiva: NO habrá edición manual de esquinas en producción.**

`manual` significa únicamente:

> el usuario pulsa físicamente el disparador en vez de permitir que AUTO capture.

La perspectiva y el recorte serán automáticos. Si no existe geometría suficientemente fiable:

1. se aplica recorte conservador, o;
2. se conserva la imagen completa.

El usuario siempre verá una **preview obligatoria** con:

- `Repetir`;
- `Usar foto`.

No se introducen handles, vértices arrastrables ni un editor fotográfico.

## 0.2. Regla de evidencia

Cada decisión de este documento pertenece a una de cuatro clases:

- **[EXISTE]**: ya existe en App2 y debe preservarse/extenderse.
- **[PORTAR SETEX]**: existe como idea o implementación útil en App1 y debe adaptarse.
- **[MERCADO]**: patrón contrastado en productos/document SDK actuales.
- **[NUEVO]**: diseño recomendado específicamente para Autoken.

Una recomendación no debe presentarse en código como si ya estuviera implantada.

## 0.3. Qué NO pretende este documento

No pretende:

- reescribir FastAPI;
- sustituir PostgreSQL;
- quitar RLS;
- sustituir Redis/arq;
- publicar objetos MinIO;
- hacer OCR inline en la petición HTTP;
- meter todos los motores OCR en cada factura;
- añadir una nueva tabla `pending_invoices` redundante;
- convertir el laboratorio en ruta crítica;
- añadir Kubernetes;
- implantar ML pesado en el VPS principal sin benchmark.

---

# 1. REALIDAD ACTUAL DE APP2 QUE DEBE PRESERVARSE

La auditoría de `develop` confirma una base sólida.

## 1.1. Intake seguro [EXISTE]

El flujo actual de `invoice_intake` ya implementa:

```text
request
→ autorización tenant/company/user
→ rate-limit
→ lectura acotada
→ validación del tipo real
→ SHA-256
→ deduplicación privada
→ antivirus fail-closed
→ MinIO privado
→ fila uploaded_files
→ audit
→ HTTP 201
```

La deduplicación actual está aislada por:

```text
(company_id, uploaded_by, sha256)
```

Esto **debe conservarse** porque evita que un usuario descubra documentos de otro compañero de la misma empresa.

## 1.2. Estados canónicos [EXISTE]

Fuente única:

`backend/src/invoice_intake/constants.py`

```python
pending_ocr
processing
ocr_done
needs_review
ocr_failed
capture_unreadable
confirmed
```

**No crear otra máquina de estados principal.**

Sí se añadirá una dimensión secundaria `processing_stage` para UX/observabilidad.

## 1.3. OCR asíncrono y recuperable [EXISTE]

App2 ya tiene:

- Redis;
- arq;
- claim antes de consumir proveedor;
- lease;
- fencing;
- recovery de `pending_ocr`;
- recovery de `processing` con lease vencido;
- persistencia final en sesión corta;
- descargas multipágina en paralelo;
- manejo de errores que no invalida una subida ya aceptada.

Esto se debe **extender, no simplificar**.

## 1.4. Validación determinista fiscal [EXISTE]

`backend/src/ocr/verification.py` ya comprueba:

```text
base × IVA% = cuota
Σbases + ΣIVA − IRPF = total
```

con `Decimal` y tolerancia monetaria por defecto de `0.02 €`.

También se reutilizan validadores de:

- NIF;
- NIE;
- CIF;
- IBAN.

Por tanto, el nuevo plan no debe “inventar un checksum fiscal” desde cero: debe **hacer más observable y granular el ya existente**.

## 1.5. Supplier master [EXISTE]

`counterparties` ya funciona como maestro de contraparte por tenant:

- cifrado por tenant;
- blind index del CIF;
- `times_seen`;
- `verified_at`;
- aislamiento por asesoría.

Esto ya es el primer nivel del “aprendizaje por proveedor”.

La mejora será añadir **patrones de proveedor por empresa** sin duplicar `counterparties`.

## 1.6. Benchmark/laboratorio [EXISTE, PERO NECESITA CORRECCIÓN]

App2 ya dispone de:

- ranking multi-modelo;
- benchmark real;
- variantes `original / enhanced / clahe`;
- persistencia de resultados;
- puntuación contra verdad confirmada;
- jobs de background;
- interruptor `ocr_experiment_enabled`.

No se reconstruye.

Se corrigen:

1. comparación estructurada de Mistral;
2. modelos Gemini obsoletos/preview en configuración;
3. separación producción/laboratorio;
4. competencia de cola entre OCR primario y experimentos;
5. política de promoción de modelo.

---

# 2. ARQUITECTURA FINAL DE PRODUCTO — VISIÓN RESUMIDA

La aplicación ofrecerá tres modos explícitos:

```text
A. 1 FACTURA
   → un documento independiente

B. VARIAS FACTURAS
   → 5–10 documentos independientes en una sesión
   → cada uno obtiene su propio uploaded_file
   → cada uno tiene su propio job OCR
   → una factura lenta no bloquea las demás

C. 1 FACTURA · VARIAS HOJAS
   → 2–5 páginas del mismo documento
   → reutiliza /api/v1/uploads/batch
```

La distinción es obligatoria.

El modo B **NO** usará `/uploads/batch`, porque ese endpoint actual representa páginas de un mismo documento.

## 2.1. Flujo objetivo de una factura

```text
/capturar
→ seleccionar Recibida/Emitida
→ seleccionar empresa si tenant_admin
→ abrir cámara
→ AUTO por defecto / MANUAL disponible
→ detección continua ligera
→ polígono amarillo
→ quality gate
→ captura HD
→ redetección HD
→ perspectiva/crop automático
→ enhancement conservador
→ preview
→ [Repetir] [Usar foto]
→ Usar foto
→ POST /api/v1/uploads
→ esperar HTTP 201
→ ✓ Guardada
→ OCR background
→ En cola
→ Verificando documento
→ Leyendo la factura
→ Comprobando datos
→ [fallback/consenso solo si necesario]
→ Casi está
→ Lista para revisar
→ /mis-facturas
→ autosave borrador
→ Confirmar y siguiente
→ creación definitiva en invoices
```

## 2.2. Flujo objetivo de 10 facturas

```text
captura #1 → preview → 201 → cámara
                       ↘ OCR #1

captura #2 → preview → 201 → cámara
                       ↘ OCR #2

...

captura #10 → preview → 201
                        ↘ OCR #10

→ abrir Mis facturas
→ revisar las ya listas
→ las restantes continúan procesando
→ Confirmar y siguiente
```

La espera del usuario se concentra en:

- el tiempo local de escaneado;
- el tiempo de upload hasta `201`.

**Nunca espera al OCR para hacer la siguiente foto.**

---

# 3. HALLAZGOS DE MERCADO QUE SE ADOPTAN COMO PATRONES

## 3.1. Dext

Dext diferencia actualmente:

- `Single`;
- `Multiple`;
- `Combine`.

Aplicación a Autoken:

```text
Single   → 1 factura
Multiple → varias facturas independientes
Combine  → 1 factura multipágina
```

No se copia su límite de 50. Para Autoken se mantiene inicialmente el objetivo de 5–10 por sesión.

## 3.2. Veryfi Lens

Patrones relevantes:

- detección documental en tiempo real;
- auto edge detection;
- auto crop;
- blur detection;
- auto capture;
- margen mínimo respecto de bordes;
- glare detection;
- preview;
- posibilidad de permitir continuar pese a señales de calidad según política.

Aplicación a Autoken:

- implementar document detection + auto capture con OpenCV existente;
- mantener botón manual;
- no bloquear manualmente por una heurística;
- glare/LCD quedan P2 experimental.

## 3.3. ABBYY Mobile Web Capture

Patrones relevantes:

```text
detección automática
→ elección del momento adecuado
→ recorte
→ corrección de perspectiva
→ OCR
```

Aplicación:

el escáner decide el momento AUTO según calidad/estabilidad; no dispara solo por encontrar cuatro puntos.

## 3.4. Regla de compra vs construcción

No se recomienda incorporar Veryfi/ABBYY/Klippa como dependencia del producto en esta fase.

Motivo:

App2 ya tiene:

- `getUserMedia`;
- OpenCV.js;
- detección;
- warpPerspective;
- PWA;
- frontend propio;
- backend propio.

Su mayor valor aquí es **validar patrones de UX y quality gate**.

---

# 4. HALLAZGOS OCR ACTUALIZADOS — DECISIONES QUE CAMBIAN EL PLAN

## 4.1. Gemini

A fecha 2026-08-21:

- `gemini-3.5-flash` es estable/GA;
- `gemini-3.6-flash` es estable y posterior;
- ambos admiten imagen/PDF y structured outputs;
- `gemini-3.5-flash-lite` está orientado a alto volumen y document extraction.

El `shared/config.py` auditado todavía usa:

```python
gemini_flash_model = "gemini-3-flash-preview"
```

Esto queda obsoleto como candidato de producción.

### Decisión

No cambiar automáticamente a 3.6 por ser más nuevo.

Primero ejecutar benchmark corregido con:

```text
gemini-3.5-flash
gemini-3.6-flash
gemini-3.5-flash-lite
```

El benchmark real de Setex dejó constancia de Gemini 3.5 Flash como ganador en su dataset.

Eso es evidencia útil, pero **no sustituye un benchmark limpio con facturas reales de Autoken**.

## 4.2. Mistral OCR 4 — hallazgo crítico

El adaptador actual:

`backend/src/ocr/engines/mistral_extractor.py`

afirma que OCR 4 solo devuelve OCR puro y, deliberadamente, crea un `ExtractedInvoice` con todos los campos estructurados a `None`.

En la API actual de Mistral existe:

```text
document_annotation_format = json_schema
document_annotation_prompt
bbox_annotation_format
confidence_scores_granularity = word | page | block
```

Por tanto:

> **el benchmark actual no es una comparación justa de extracción estructurada entre Mistral y Gemini.**

### Requisito bloqueante

Antes de decidir si Mistral “es peor”:

1. implementar annotation JSON Schema real;
2. mapearlo al mismo contrato canónico;
3. volver a ejecutar el benchmark;
4. separar OCR 4.0 GA de OCR 4.1 Preview.

## 4.3. Open-source

### PaddleOCR / PP-StructureV3

Ventajas:

- layout;
- reading order;
- tablas;
- unwarping;
- orientación;
- OCR;
- resultados JSON/Markdown.

Coste:

- pila ML mucho más pesada;
- múltiples modelos;
- CPU/GPU/memoria;
- complejidad operacional.

Decisión:

> **laboratorio P2 como servicio separado**, no importarlo dentro del proceso FastAPI/ARQ principal.

### Surya

Ventajas:

- OCR;
- layout;
- reading order;
- tablas;
- 90+ idiomas.

Decisión:

> challenger P2 en contenedor/servicio aislado; no ruta crítica inicial.

### Tesseract

Ventaja principal:

- OCR local;
- sin coste por llamada;
- útil para comprobar si un CIF/número/importe propuesto aparece realmente en el texto.

Decisión:

> no será extractor fiscal principal. Se evaluará como `local_evidence_checker` background/parallel.

### scikit-image

Útil para experimentar con:

- CLAHE;
- Sauvola;
- Niblack;
- thresholding local.

Decisión:

> usar en laboratorio offline para encontrar transformaciones ganadoras; si una gana, portar la operación a OpenCV ya existente en frontend/backend en vez de añadir scikit-image a producción.

### jscanify

jscanify aporta:

- `findPaperContour`;
- `highlightPaper`;
- `extractPaper`;
- `getCornerPoints`.

App2 ya dispone de un detector OpenCV más avanzado con:

- Otsu;
- Canny;
- morphological close;
- `approxPolyDP`;
- `convexHull`;
- `minAreaRect`;
- `warpPerspective`.

Decisión:

> no añadir jscanify como dependencia runtime. Usarlo como referencia algorítmica/UX y benchmark de detección si se desea.

---

# 5. SISTEMA DE PRIORIZACIÓN

Cada requisito se valora con:

- **Prioridad:** P0 / P1 / P2 / P3.
- **Dependencia:** requisito(s) que deben existir antes.
- **Impacto:** 1–5.
- **Esfuerzo:** 1–5.
- **Riesgo:** 1–5.
- **Beneficio/coste:** Alto / Medio / Bajo.

### Definiciones

| Prioridad | Significado |
|---|---|
| P0 | bloqueante para el nuevo flujo o para seguridad/corrección |
| P1 | necesario para producción profesional |
| P2 | optimización importante, activable después de medir |
| P3 | laboratorio/innovación sin bloquear lanzamiento |

---


# 6. REQUISITOS MAESTROS ORDENADOS POR DEPENDENCIAS

La columna **Nivel** es un orden topológico: un nivel superior no debe implementarse antes de sus dependencias.

| ID | Pri. | Nivel | Requisito | Depende de | Impacto | Esfuerzo | Riesgo | Beneficio/coste |
|---|---|---:|---|---|---:|---:|---:|---|
| R-000 | P0 | 0 | Congelar baseline y verificar rama/migraciones/tests actuales | — | 5 | 1 | 1 | Alto |
| R-001 | P0 | 0 | Resolver precedencia de specs: AUTO/MANUAL sí; editor manual de esquinas no | R-000 | 5 | 1 | 1 | Alto |
| R-002 | P0 | 1 | Separar modos Single / Continuous / Multipage | R-001 | 5 | 2 | 1 | Alto |
| R-003 | P0 | 1 | Definir tipos normalizados de scanner y configuración central | R-001 | 5 | 2 | 2 | Alto |
| R-004 | P1 | 2 | Mover análisis continuo de cámara a Web Worker con máximo 1 frame en vuelo | R-003 | 4 | 4 | 3 | Medio/alto |
| R-005 | P0 | 2 | Mejorar detección de documento con candidate scoring + confidence | R-003 | 5 | 4 | 3 | Alto |
| R-006 | P0 | 3 | Quality gate puro: área, blur ROI, exposición, clipping, perspectiva, estabilidad | R-005 | 5 | 3 | 2 | Alto |
| R-007 | P0 | 3 | AUTO por defecto + MANUAL siempre disponible + lock único de captura | R-006 | 5 | 3 | 2 | Alto |
| R-008 | P0 | 3 | Overlay SVG amarillo y mensajes contextuales | R-005 | 4 | 2 | 2 | Alto |
| R-009 | P0 | 4 | Captura HD + redetección HD + crop/perspectiva automática conservadora | R-005,R-007 | 5 | 4 | 3 | Alto |
| R-010 | P0 | 4 | Preview obligatoria Repetir / Usar foto sin editor de esquinas | R-009 | 5 | 3 | 1 | Alto |
| R-011 | P0 | 5 | Refactor upload: esperar 201, no esperar OCR, volver a cámara | R-010 | 5 | 3 | 2 | Alto |
| R-012 | P0 | 5 | Captura continua 5–10 invoices, cada una uploaded_file independiente | R-002,R-011 | 5 | 4 | 2 | Alto |
| R-013 | P1 | 5 | Añadir capture_session_id + capture_sequence sin nueva pending table | R-012 | 4 | 3 | 2 | Alto |
| R-014 | P0 | 6 | No navegar automáticamente a /confirmar tras upload | R-011 | 5 | 1 | 1 | Alto |
| R-015 | P0 | 6 | Mantener stream de cámara tras 201 | R-011 | 4 | 2 | 3 | Alto |
| R-016 | P0 | 6 | Persistir processing_stage y timestamps OCR sin cambiar FileStatus canónico | R-000 | 5 | 3 | 2 | Alto |
| R-017 | P0 | 7 | Instrumentar stages con fencing: queued/loading/primary/validating/fallback/consensus/persisting | R-016 | 5 | 3 | 2 | Alto |
| R-018 | P0 | 7 | Componente de progreso real con textos Verificando/Procesando/Casi está | R-017 | 5 | 3 | 1 | Alto |
| R-019 | P1 | 7 | Endpoint/status DTO e inbox agregada sin polling por fila | R-016 | 5 | 3 | 2 | Alto |
| R-020 | P0 | 8 | Nueva bandeja /mis-facturas SELF ONLY | R-019 | 5 | 4 | 3 | Alto |
| R-021 | P0 | 8 | review_drafts cifrado + RLS + owner guard | R-000 | 5 | 5 | 4 | Alto |
| R-022 | P0 | 9 | Autosave 750ms snapshot completo con revision/409 | R-021 | 5 | 4 | 3 | Alto |
| R-023 | P0 | 9 | Review prioriza draft sobre OCR | R-021 | 5 | 3 | 2 | Alto |
| R-024 | P0 | 10 | Confirmación atómica guarda invoice y borra draft | R-022,R-023 | 5 | 4 | 3 | Alto |
| R-025 | P1 | 10 | Confirmar y siguiente después del commit | R-020,R-024 | 4 | 2 | 2 | Alto |
| R-026 | P1 | 10 | Panel tenant_admin de supervisión read-only de pendientes ajenos | R-020,R-021 | 4 | 4 | 4 | Medio/alto |
| R-027 | P1 | 10 | Admin-tech global: metadata + apertura explícita read-only auditada | R-020 | 4 | 4 | 5 | Medio |
| R-028 | P1 | 10 | Retención 90 días y purge diario seguro DB→commit→MinIO | R-021 | 4 | 4 | 4 | Alto |
| R-029 | P0 | 1 | Corregir benchmark Mistral con document_annotation JSON Schema | R-000 | 5 | 4 | 3 | Alto |
| R-030 | P0 | 1 | Actualizar candidatos Gemini 3.5/3.6/3.5-Lite sin auto-promoción | R-000 | 5 | 2 | 2 | Alto |
| R-031 | P0 | 2 | Contrato Pydantic InvoiceExtractionSchema versionado para motores | R-029,R-030 | 5 | 4 | 3 | Alto |
| R-032 | P0 | 3 | Benchmark comparable: mismo dataset/schema/normalización/campos/latencia/coste | R-031 | 5 | 4 | 3 | Alto |
| R-033 | P0 | 4 | Política OCR producción: motor primario fijo administrable | R-032 | 5 | 3 | 3 | Alto |
| R-034 | P1 | 5 | Fallback condicional por timeout/error/duda/validación, no doble OCR permanente | R-033 | 5 | 4 | 3 | Alto |
| R-035 | P1 | 6 | Consenso por campo normalizado entre primario y fallback | R-034 | 5 | 5 | 4 | Alto |
| R-036 | P1 | 7 | Confidence fusion numérica + reason codes | R-035 | 5 | 5 | 4 | Alto |
| R-037 | P0 | 5 | Extender fiscal diagnostics sin reimplementar checksum existente | R-031 | 5 | 3 | 2 | Alto |
| R-038 | P1 | 7 | Supplier intelligence por tenant+company+counterparty | R-024,R-037 | 5 | 5 | 4 | Alto |
| R-039 | P2 | 8 | Tesseract local_evidence_checker aislado/paralelo/background | R-036 | 3 | 4 | 3 | Medio |
| R-040 | P2 | 8 | Experimentos preprocess CLAHE/Sauvola/Natural/Gray/BW con dataset | R-032 | 3 | 3 | 2 | Medio |
| R-041 | P3 | 9 | PaddleOCR PP-StructureV3 challenger en servicio separado | R-032 | 2 | 5 | 4 | Bajo/medio |
| R-042 | P3 | 9 | Surya challenger en servicio separado | R-032 | 2 | 5 | 4 | Bajo/medio |
| R-043 | P1 | 5 | Separar cola OCR primaria de background lab/benchmark | R-033 | 5 | 4 | 3 | Alto |
| R-044 | P1 | 6 | ocr_worker_max_jobs configurable y calibrado | R-043 | 4 | 2 | 3 | Alto |
| R-045 | P1 | 7 | Circuit breaker/fallo proveedor y backoff sin tormenta de fallback | R-034,R-043 | 4 | 4 | 4 | Alto |
| R-046 | P1 | 7 | Separar controles admin-tech Producción OCR vs Laboratorio | R-033,R-043 | 5 | 4 | 3 | Alto |
| R-047 | P1 | 8 | SLO/telemetría p50/p95 upload, queue, OCR, draft, review | R-016,R-020 | 5 | 3 | 2 | Alto |
| R-048 | P2 | 9 | ETA solo cuando haya muestra suficiente; nunca falsa precisión | R-047 | 3 | 3 | 2 | Medio |
| R-049 | P1 | 10 | Security regression suite IDOR/RLS/PII/cache/storage | R-020,R-021,R-027 | 5 | 5 | 3 | Alto |
| R-050 | P1 | 10 | Carga 10 usuarios × 10 invoices + degradación controlada | R-043,R-047 | 5 | 4 | 3 | Alto |
| R-051 | P1 | 11 | Rollout por feature flags/canario + rollback por fase | R-049,R-050 | 5 | 3 | 2 | Alto |
| R-052 | P1 | 10 | Revisión controlada, borrado seguro, deduplicación y medición de captura | R-020,R-022,R-024,R-025,R-049 | 5 | 5 | 3 | Alto |
| R-053 | P2 | 9 | Paleta clara del app shell sin cambios funcionales | R-049,R-052 | 3 | 2 | 1 | Medio |



## 6.1. Camino crítico mínimo hasta producción

```text
R-000 baseline
├─ R-001 precedencia
│  ├─ R-002 modos
│  └─ R-003 scanner types
│     └─ R-005 detector
│        └─ R-006 quality gate
│           └─ R-007 auto/manual
│              └─ R-009 still HD
│                 └─ R-010 preview
│                    └─ R-011 upload→201
│                       └─ R-012 captura continua
│                          └─ R-020 inbox
│
├─ R-016 progress stage
│  └─ R-017 stage updates
│     └─ R-018 progress UI
│
├─ R-021 drafts
│  └─ R-022 autosave
│     └─ R-024 confirm
│
└─ R-029/R-030 modelo candidates
   └─ R-031 schema
      └─ R-032 fair benchmark
         └─ R-033 primary policy
            └─ R-034 fallback
```

## 6.2. Regla de implementación

No iniciar:

- `supplier_profiles` antes de estabilizar confirmación/draft;
- consenso antes de tener un benchmark comparable;
- ETA antes de tener telemetría;
- Paddle/Surya antes de estabilizar el pipeline cloud;
- background upload/IndexedDB antes de medir `upload→201`.

---

# 7. FASE 0 — BASELINE, GUARDARRAÍLES Y DOCUMENTACIÓN

## REQ R-000 — Baseline reproducible

### Objetivo

Evitar implementar sobre una rama cuyo estado real no conocemos.

### Antes de tocar código

Ejecutar:

```bash
git checkout develop
git pull --ff-only
git status
git rev-parse HEAD

cd backend
alembic heads
alembic current
pytest

cd ../frontend
npm ci
npm run typecheck
npm run test
npm run build
```

### Criterios

- working tree limpio;
- exactamente un Alembic head;
- tests actuales verdes;
- build frontend verde.

### Migraciones

La auditoría actual muestra como último fichero:

```text
0040_ocr_irpf_fields.py
```

Los nombres propuestos `0041+` de este documento son **orientativos**.

Regla obligatoria:

> verificar `alembic heads` justo antes de crear cada migración; nunca asumir que 0041 sigue libre.

## REQ R-001 — Nueva spec de precedencia

Crear:

```text
docs/specs/S6.XX-master-autofactu-production.md
```

Este documento puede copiarse allí como fuente.

Debe declarar explícitamente:

```text
AUTO default
MANUAL fallback
NO manual corner editing
preview mandatory
continuous invoices != multipage invoice
upload waits 201
OCR is async
invoice definitive only on confirm
```

---

# 8. FASE 1 — MODOS DE CAPTURA

## REQ R-002 — Tres modos de producto

### Frontend

Modificar:

```text
frontend/src/features/capture/types.ts
```

Añadir:

```ts
export type CaptureProductMode =
  | 'single_invoice'
  | 'continuous_invoices'
  | 'multipage_invoice'

export type CaptureMode = 'auto' | 'manual'
```

### UI

En `/capturar` mostrar tres acciones claras:

```text
[ 1 factura ]
[ Varias facturas ]
[ 1 factura · varias hojas ]
```

### Mapping

| UI | Backend | Semántica |
|---|---|---|
| 1 factura | `POST /uploads` | 1 uploaded_file |
| Varias facturas | N × `POST /uploads` | N uploaded_files |
| 1 factura · varias hojas | `POST /uploads/batch` | 1 root + páginas |

### Prueba de aceptación

Capturar 3 documentos en “Varias facturas” debe devolver 3 `file_id` distintos.

Capturar 3 hojas en “Varias hojas” debe devolver 1 `file_id`.

---

# 9. FASE 2 — ESCÁNER DOCUMENTAL INTELIGENTE

## REQ R-003 — Tipos normalizados

Modificar:

```text
frontend/src/features/capture/types.ts
```

Reemplazar progresivamente `Corner` de píxel como tipo interno dominante por:

```ts
export interface NormalizedPoint {
  x: number // [0,1]
  y: number // [0,1]
}

export type NormalizedCorners = readonly [
  NormalizedPoint, // top-left
  NormalizedPoint, // top-right
  NormalizedPoint, // bottom-right
  NormalizedPoint, // bottom-left
]

export type DetectionMethod =
  | 'approx'
  | 'hull'
  | 'min_area_rect'
  | null

export interface DocumentDetection {
  corners: NormalizedCorners | null
  confidence: number
  areaRatio: number
  method: DetectionMethod
}

export interface CaptureQuality {
  sharpness: number
  meanLuminance: number
  darkPixelRatio: number
  brightPixelRatio: number
  areaRatio: number
  detectionConfidence: number
  stabilityScore: number
  perspectiveScore: number
  clipped: boolean
}

export interface FrameAnalysis {
  detection: DocumentDetection
  quality: CaptureQuality
}
```

Los píxeles solo se materializan al dibujar/procesar.

### Motivo

La normalización desacopla:

- resolución de análisis;
- resolución HD;
- viewport móvil;
- orientación;
- `object-cover`.

## REQ R-003B — Config central del scanner

Crear:

```text
frontend/src/features/capture/scannerConfig.ts
```

```ts
export interface ScannerConfig {
  analysisIntervalMs: number
  previewLongEdgePx: number
  stillAnalysisLongEdgePx: number
  detectionMinAreaRatio: number
  autoMinAreaRatio: number
  autoMinDetectionConfidence: number
  minFrameMarginRatio: number
  maxPerspectiveRatio: number
  stableRequiredMs: number
  stableMinFrames: number
  maxCornerMovementRatio: number
  maxAreaVariationRatio: number
  autoCaptureConfirmationMs: number
}

export const DEFAULT_SCANNER_CONFIG: ScannerConfig = {
  analysisIntervalMs: 200,
  previewLongEdgePx: 720,
  stillAnalysisLongEdgePx: 1600,
  detectionMinAreaRatio: 0.15,
  autoMinAreaRatio: 0.30,
  autoMinDetectionConfidence: 0.75,
  minFrameMarginRatio: 0.02,
  maxPerspectiveRatio: 2.2,
  stableRequiredMs: 700,
  stableMinFrames: 4,
  maxCornerMovementRatio: 0.012,
  maxAreaVariationRatio: 0.04,
  autoCaptureConfirmationMs: 350,
}
```

Estos son **valores iniciales**, no verdades universales.

Deben quedar benchmarkeables.

---

# 10. FASE 3 — COORDENADAS Y OVERLAY

## REQ R-008 — Polígono amarillo

Crear:

```text
frontend/src/features/capture/DocumentOverlay.tsx
frontend/src/features/capture/coordinates.ts
frontend/src/features/capture/coordinates.test.ts
```

### `object-cover`

Implementar explícitamente:

```ts
const scale = Math.max(
  containerWidth / sourceWidth,
  containerHeight / sourceHeight,
)

const renderedWidth = sourceWidth * scale
const renderedHeight = sourceHeight * scale
const offsetX = (containerWidth - renderedWidth) / 2
const offsetY = (containerHeight - renderedHeight) / 2

screenX = sourceX * scale + offsetX
screenY = sourceY * scale + offsetY
```

### Funciones mínimas

```ts
sourcePointToScreen()
screenPointToSource()
normalizedPointToScreen()
screenPointToNormalized()
```

### `DocumentOverlay`

SVG:

```tsx
<svg
  aria-hidden="true"
  className="pointer-events-none absolute inset-0 h-full w-full"
>
  {points && (
    <polygon
      points={points}
      fill="rgba(255,212,0,0.08)"
      stroke="#FFD400"
      strokeWidth="3"
      vectorEffect="non-scaling-stroke"
    />
  )}
</svg>
```

### Estados

```text
no detection       → guía tenue
detected           → amarillo
quality good       → amarillo intenso
stabilizing        → progreso
auto armed         → confirmación visual
```

### No hacer

- canvas de pantalla completa a 60 FPS;
- dibujar coordenadas raw sin compensar `object-cover`;
- re-renderizar React en todos los frames de vídeo.

---

# 11. FASE 4 — DETECCIÓN CONTINUA Y WEB WORKER

## REQ R-004 — Scanner Worker

Crear:

```text
frontend/src/features/capture/scanner.worker.ts
frontend/src/features/capture/useScannerEngine.ts
frontend/src/features/capture/scannerProtocol.ts
```

### Regla crítica

```text
máximo 1 análisis en vuelo
```

No se crea una cola de frames.

Si el worker está ocupado:

```text
frame nuevo → drop
```

Cuando queda libre:

```text
procesar el frame más reciente
```

### Protocolo

```ts
export type ScannerWorkerRequest =
  | { type: 'INIT'; requestId: number }
  | {
      type: 'ANALYZE_PREVIEW'
      requestId: number
      image: ImageBitmap
      sourceWidth: number
      sourceHeight: number
    }
  | {
      type: 'ANALYZE_STILL'
      requestId: number
      image: ImageBitmap
    }
  | {
      type: 'PROCESS_FINAL'
      requestId: number
      image: ImageBitmap
      corners: NormalizedCorners | null
      filter: 'natural'
    }

export type ScannerWorkerResponse =
  | { type: 'READY'; requestId: number }
  | { type: 'PREVIEW_ANALYSIS'; requestId: number; analysis: FrameAnalysis }
  | { type: 'STILL_ANALYSIS'; requestId: number; analysis: FrameAnalysis }
  | { type: 'PROCESSED_FINAL'; requestId: number; blob: Blob }
  | { type: 'ERROR'; requestId: number; code: string }
```

### Stale result guard

`useScannerEngine.ts` debe ignorar respuestas cuyo `requestId` sea anterior al activo.

### Captura de preview

Ruta preferente:

```text
requestVideoFrameCallback
→ createImageBitmap
→ resize
→ transfer worker
```

Fallback:

```text
setTimeout
→ canvas
→ ImageData
```

Nunca hacer de `requestVideoFrameCallback` una dependencia obligatoria.

---

# 12. FASE 5 — DETECTOR MEJORADO

## REQ R-005 — No elegir solo “el contorno más grande”

Modificar:

```text
frontend/src/features/capture/opencv/documentEdges.ts
```

Mantener el pipeline actual:

```text
RGBA
→ grayscale
→ GaussianBlur
→ Otsu
→ Canny
→ morphological close
→ findContours
```

Cambiar la elección de candidato.

### Score propuesto

```ts
interface CandidateFeatures {
  areaRatio: number
  rectangularity: number
  convexity: number
  centerScore: number
  edgeContinuity: number
  marginScore: number
  aspectPlausibility: number
  method: DetectionMethod
}
```

```ts
candidateScore =
    0.28 * area
  + 0.20 * rectangularity
  + 0.12 * convexity
  + 0.10 * center
  + 0.12 * edgeContinuity
  + 0.10 * margin
  + 0.08 * aspectPlausibility
```

Los pesos iniciales son calibrables.

### Confianza por método

Aplicar un `methodPrior`:

```text
approxPolyDP 4 corners → 1.00
convexHull + approx    → 0.85
minAreaRect            → 0.60
```

`minAreaRect` puede guiar y ayudar al disparo manual.

Para AUTO necesita señales adicionales fuertes.

### Tests

- mesa rectangular no debe ganar a una factura centrada;
- factura oblicua válida sí se detecta;
- sombra que rompe un borde se recupera mediante morphology;
- objeto pequeño rectangular no supera área mínima;
- `confidence` siempre [0,1].

---

# 13. FASE 6 — QUALITY GATE Y AUTO-CAPTURA

## REQ R-006 — `qualityGate.ts`

Crear:

```text
frontend/src/features/capture/qualityGate.ts
frontend/src/features/capture/qualityGate.test.ts
```

Debe ser puro.

```ts
export type AutoCaptureReason =
  | 'no_document'
  | 'low_confidence'
  | 'too_small'
  | 'clipped'
  | 'blurry'
  | 'too_dark'
  | 'too_bright'
  | 'perspective_extreme'
  | 'moving'
  | 'ready'

export interface AutoCaptureDecision {
  ready: boolean
  reason: AutoCaptureReason
}
```

### Reglas AUTO

```text
documentDetected
AND detectionConfidence >= threshold
AND area >= threshold
AND !clipped
AND sharpnessOK
AND exposureOK
AND perspectiveOK
AND stableLongEnough
```

### Nitidez

No usar el frame completo.

Calcular sobre ROI del documento:

```text
corners
→ mask / bounding ROI
→ grayscale
→ Laplacian
→ variance
```

Esto evita que una mesa texturada falsee la nitidez.

### Exposición

Añadir:

```text
meanLuminance
darkPixelRatio   // lum < 15
brightPixelRatio // lum > 245
```

### Perspectiva

```ts
horizontalRatio = max(top, bottom) / min(top, bottom)
verticalRatio = max(left, right) / min(left, right)
perspectiveRatio = Math.max(horizontalRatio, verticalRatio)
```

Inicial:

```text
max = 2.2
```

### Clipping

Cualquier esquina dentro de la banda:

```text
< 2% del borde
```

marca `clipped=true`.

### Estabilidad

Guardar historial reciente de detecciones.

AUTO exige:

```text
>= 700 ms
AND >= 4 frames válidos
AND corner movement <= 0.012 diagonal
AND area variation <= 0.04
```

## REQ R-007 — Auto/manual reducer

Refactorizar:

```text
frontend/src/features/capture/captureLoop.ts
```

El reducer actual es manual.

Nueva máquina:

```ts
export type ScannerPhase =
  | 'scanning'
  | 'valid'
  | 'stabilizing'
  | 'auto_armed'
  | 'capturing'
  | 'still_processing'
  | 'preview'
  | 'uploading'
  | 'accepted'
  | 'error'
```

### CaptureMode

```text
camera open → auto
AUTO→MANUAL → reset stability/timer/armed
MANUAL→AUTO → reset stability/timer/armed
```

No persistir inicialmente en localStorage.

### Lock único

AUTO y MANUAL comparten:

```ts
const captureLockRef = useRef(false)
```

Nunca pueden crear dos uploads por un doble evento.

---

# 14. FASE 7 — CAPTURA HD Y PROCESADO FINAL

## REQ R-009

Modificar/extender:

```text
frontend/src/features/capture/grabVideoFrame.ts
frontend/src/features/capture/processCapture.ts
frontend/src/features/capture/normalizeToJpeg.ts
```

### Separar resoluciones

```text
preview analysis → long edge ~720
still analysis   → long edge 1200–1600
final output     → resolución HD útil
```

### Captura

Mejora progresiva:

```ts
if ('ImageCapture' in window) {
  // takePhoto()
} else {
  // canvas fallback
}
```

No romper Safari/iOS.

### Redetección

El polígono de preview NO se reutiliza como verdad definitiva.

```text
HD still
→ copia 1200–1600
→ detectDocumentCorners
→ normalized corners
→ validación geométrica
→ warp si fiable
→ si no fiable: crop conservador o full image
```

## REQ R-010 — Preview obligatoria

Crear preferentemente:

```text
frontend/src/features/capture/CapturePreview.tsx
```

Acciones:

```text
[ Repetir ] [ Usar foto ]
```

`Repetir`:

- revoca ObjectURL;
- cierra ImageBitmap;
- elimina Blob temporal;
- vuelve a cámara;
- NO llama backend.

`Usar foto`:

- lock;
- muestra `Guardando factura…`;
- POST;
- espera 201;
- muestra `✓ Guardada`;
- vuelve a cámara o cierra si modo single.

### No incluir

- draggable corners;
- sliders;
- filtros seleccionables de cara al usuario;
- editor fotográfico.

---

# 15. FASE 8 — PREPROCESADO DOCUMENTAL

## 15.1. Filtro de producción inicial

Producción debe usar un filtro:

```text
natural_document
```

con transformaciones conservadoras.

No convertir por defecto todo a B/N.

Motivo:

- puede destruir caracteres finos;
- puede borrar sellos/color útil;
- puede degradar VLMs modernos.

## 15.2. Benchmark de variantes

Dataset fijo con verdad humana.

Comparar:

```text
raw/crop only
natural
CLAHE
gray
Sauvola/BW
```

Medir:

- acierto campo a campo;
- `all_fields_exact`;
- CIF;
- número factura;
- fecha;
- bases;
- IVA;
- total;
- IRPF;
- tiempo CPU;
- tamaño bytes;
- OCR latency;
- coste API.

## 15.3. scikit-image

Usarlo solo en scripts/notebooks de benchmark:

```text
tools/image_bench/
```

No añadirlo al backend runtime para duplicar OpenCV/Pillow.

Si CLAHE o Sauvola gana:

> portar los parámetros/algoritmo al OpenCV que ya está en el proyecto.

---

# 16. FASE 9 — CAPTURA CONTINUA 5–10 FACTURAS

## REQ R-012 — Sesión continua

La sesión no equivale a un documento multipágina.

### Estado frontend

Crear:

```text
frontend/src/features/capture/continuousCapture.ts
```

```ts
export interface ContinuousCaptureState {
  sessionId: string
  accepted: Array<{
    fileId: string
    sequence: number
    acceptedAt: string
  }>
  currentSequence: number
  maxItems: number
}
```

Inicial:

```text
maxItems = 10
```

No es necesario obligar a llegar a 10.

## REQ R-013 — Agrupación durable ligera

Añadir opcionalmente a `uploaded_files`:

```sql
capture_session_id uuid NULL,
capture_sequence smallint NULL
```

Constraint:

```sql
CHECK (
  (capture_session_id IS NULL AND capture_sequence IS NULL)
  OR
  (capture_session_id IS NOT NULL AND capture_sequence BETWEEN 1 AND 50)
)
```

Índice:

```sql
CREATE INDEX ix_uploaded_files_capture_session
ON uploaded_files (tenant_id, uploaded_by, capture_session_id, capture_sequence)
WHERE capture_session_id IS NOT NULL;
```

### Importante

No crear `capture_sessions` todavía.

El `sessionId` es agrupación UX, no autoridad.

Autorización siempre deriva de:

```text
JWT + tenant + uploaded_by + RLS
```

### API

Ampliar multipart de `POST /uploads` con:

```text
capture_session_id?
capture_sequence?
```

El backend:

- valida UUID;
- valida rango;
- guarda;
- nunca lo usa para saltarse scopes.

## REQ R-015 — Mantener cámara

`CaptureScreen.tsx` no debe ejecutar `stopCamera()` después de cada disparo aceptado en modo continuous.

En cambio:

```text
camera stream
→ capture
→ preview
→ uploading
→ 201
→ resume stream
```

Si el navegador ha suspendido track, revalidar `readyState`.

---

# 17. FASE 10 — REFACTORIZACIÓN DE UPLOAD

## REQ R-011

Refactorizar:

```text
frontend/src/features/capture/useUploadCapture.ts
```

Separar transporte de hooks:

```ts
export async function uploadCapture(...)
export async function uploadMultipageCapture(...)
```

El hook podrá envolver esas funciones con TanStack Mutation.

### Resultado

```ts
export interface AcceptedUpload {
  id: string
  duplicate: boolean
}
```

### Duplicado

Mantener el comportamiento actual:

```text
409 duplicate_of
→ se trata como referencia al existente
```

pero en captura continua debe indicar discretamente:

```text
“Esta factura ya estaba subida”
```

y no agregar dos veces el mismo `fileId` a la sesión visual.

## REQ R-014 — Quitar navegación directa

Modificar:

```text
frontend/src/app/AppRoutes.tsx
```

Ancla actual:

```text
CaptureRoute → onUploaded → navigate(confirmation)
```

Nuevo:

```text
single:
  201 → mostrar accepted → ofrecer “Revisar cuando esté lista” / ir a Mis facturas

continuous:
  201 → camera

multipage:
  201 → Mis facturas o estado del documento
```

No abrir revisión bloqueando mientras OCR corre.

---

# 18. FASE 11 — PROGRESO REAL “VERIFICANDO / PROCESANDO / CASI ESTÁ”

## REQ R-016 — `processing_stage`

El `FileStatus` actual debe permanecer.

Añadir una segunda dimensión:

```python
class ProcessingStage(StrEnum):
    QUEUED = "queued"
    LOADING_DOCUMENT = "loading_document"
    PRIMARY_OCR = "primary_ocr"
    VALIDATING = "validating"
    FALLBACK_OCR = "fallback_ocr"
    CONSENSUS = "consensus"
    PERSISTING = "persisting"
```

### Dónde

Crear:

```text
backend/src/invoice_intake/processing.py
```

o mantener cerca de `constants.py`, pero no mezclarlo con status final.

### DB

`uploaded_files`:

```sql
processing_stage text NULL,
ocr_started_at timestamptz NULL,
ocr_finished_at timestamptz NULL
```

Constraint:

```sql
processing_stage IS NULL OR processing_stage IN (...)
```

## REQ R-017 — Actualización con fencing

Añadir repository method:

```text
backend/src/invoice_intake/repository.py
```

```python
async def update_processing_stage(
    session,
    file_id: UUID,
    *,
    claim_token: UUID,
    stage: ProcessingStage,
) -> bool:
    ...
```

SQL conceptual:

```sql
UPDATE uploaded_files
SET processing_stage = :stage
WHERE id = :file_id
  AND ocr_claim_token = :claim_token
  AND status = 'processing';
```

Nunca permitir que un worker antiguo cambie el stage.

### Puntos concretos en `jobs/ocr.py`

Ancla `run_ocr`.

```text
claim aceptado
→ stage loading_document
→ set ocr_started_at

antes de primary extractor
→ primary_ocr

después de extracción, antes de analysis
→ validating

solo si fallback
→ fallback_ocr

solo si reconciliación de >1
→ consensus

antes de persistir resultado final
→ persisting

final
→ stage NULL
→ ocr_finished_at NOW()
```

### Número de writes

Máximo normal sin fallback:

```text
4–5 updates
```

No actualizar progreso por token ni por porcentaje.

## REQ R-018 — Progress UI

Crear:

```text
frontend/src/features/processing/ProcessingProgress.tsx
frontend/src/features/processing/progressModel.ts
frontend/src/features/processing/progressModel.test.ts
```

### Mapping UX

| stage/status | Texto principal | Subtexto | progreso visual |
|---|---|---|---:|
| pending_ocr/queued | En cola | Hemos guardado la factura | 12% |
| loading_document | Verificando documento | Preparando la imagen de forma segura | 22% |
| primary_ocr | Procesando factura | Leyendo los datos | 48% |
| validating | Comprobando datos | Revisando CIF, importes e impuestos | 70% |
| fallback_ocr | Verificando una duda | Contrastando los campos dudosos | 80% |
| consensus | Contrastando resultados | Eligiendo el dato más fiable | 88% |
| persisting | Casi está | Guardando el resultado para revisión | 96% |
| ocr_done | Lista para revisar | — | 100% |
| needs_review | Lista para revisar | Hay algún dato que conviene comprobar | 100% |
| capture_unreadable | Repite la foto | No se pudo leer con fiabilidad | — |
| ocr_failed | No pudimos completar la lectura | Puedes reintentar | — |

### Regla UX

La barra representa **etapas reales**, no tiempo ficticio.

El porcentaje es discreto/monótono.

Si un backend antiguo no devuelve `processing_stage`:

```text
mostrar spinner/indeterminate
```

### Accesibilidad

```tsx
<div
  role="progressbar"
  aria-valuemin={0}
  aria-valuemax={100}
  aria-valuenow={percent}
/>
<p aria-live="polite">{message}</p>
```

No cambiar `aria-live` 10 veces por segundo.

---

# 19. FASE 12 — ENDPOINT DE STATUS E INBOX

## REQ R-019 — Status pequeño

Crear endpoint:

```http
GET /api/v1/uploads/{file_id}/status
```

Respuesta:

```json
{
  "id": "uuid",
  "status": "processing",
  "processing_stage": "primary_ocr",
  "created_at": "...",
  "ocr_started_at": "...",
  "ocr_finished_at": null
}
```

No devolver:

- PII;
- raw OCR;
- bucket;
- storage_key;
- sha256.

### Auth

Misma autorización de objeto que descarga/review.

Para `user`, fichero ajeno:

```text
404
```

## REQ R-020 — `/mis-facturas`

Nueva ruta:

```text
/mis-facturas
```

Backend:

```http
GET /api/v1/invoices/inbox
```

Semántica:

```text
SELF ONLY
```

incluso para `tenant_admin`.

### DTO

```json
{
  "items": [
    {
      "id": "uuid",
      "status": "processing",
      "processing_stage": "primary_ocr",
      "created_at": "...",
      "direction": "recibida",
      "page_count": 1,
      "capture_session_id": "uuid",
      "capture_sequence": 3,
      "draft_updated_at": null
    }
  ],
  "summary": {
    "processing": 2,
    "ready": 4,
    "attention": 1
  },
  "next_cursor": null
}
```

### Sin PII

No listar:

- CIF;
- proveedor;
- número factura;
- importes;
- OCR raw.

### Orden

```sql
ORDER BY created_at DESC, id DESC
```

Cursor compuesto.

### Polling

Una petición agregada:

```text
processing > 0 → refetchInterval 2000
processing = 0 → false
```

Además:

```text
refetchOnWindowFocus
refetchOnReconnect
```

Prohibido `1 timer × card`.

### Ruta frontend

Añadir:

```text
frontend/src/features/inbox/InvoiceInbox.tsx
frontend/src/features/inbox/useInvoiceInbox.ts
frontend/src/features/inbox/InboxItem.tsx
```

Y en:

```text
frontend/src/app/routes.ts
frontend/src/app/AppRoutes.tsx
```

---

# 20. FASE 13 — REVIEW DRAFTS Y AUTOSAVE

## REQ R-021 — Tabla `review_drafts`

No es una factura.

Es el estado editable previo a confirmación.

Migración propuesta, sujeto a head real:

```text
0042_review_drafts.py
```

### Esquema conceptual

```sql
CREATE TABLE review_drafts (
    uploaded_file_id uuid PRIMARY KEY
        REFERENCES uploaded_files(id) ON DELETE CASCADE,

    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    owner_user_id uuid NOT NULL,

    direction text NULL,
    issue_date date NULL,
    invoice_number text NULL,

    counterparty_tax_id bytea NULL,
    counterparty_tax_id_blind_index text NULL,
    counterparty_name bytea NULL,

    net_amount numeric NULL,
    tax_amount numeric NULL,
    total_amount numeric NULL,
    irpf_amount numeric NULL,
    tax_lines jsonb NOT NULL DEFAULT '[]'::jsonb,

    revision integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

### Cifrado

Reutilizar:

```text
shared/encryption.py
tenant_encryption_key
blind index
```

No inventar otro cifrado.

### RLS

```sql
ALTER TABLE review_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE review_drafts FORCE ROW LEVEL SECURITY;
```

Seguir patrón de migraciones actuales.

Además de RLS, el servicio impone propietario para user.

## REQ R-022 — PUT draft

```http
PUT /api/v1/uploads/{file_id}/draft
```

Body snapshot:

```json
{
  "revision": 3,
  "direction": "recibida",
  "issue_date": "2026-08-21",
  "invoice_number": "F-123",
  "counterparty_tax_id": "B...",
  "counterparty_name": "...",
  "net_amount": "100.00",
  "tax_amount": "21.00",
  "total_amount": "121.00",
  "irpf_amount": null,
  "tax_lines": [...]
}
```

Success:

```json
{
  "revision": 4,
  "updated_at": "..."
}
```

Conflict:

```http
409
```

```json
{
  "detail": {
    "code": "draft_revision_conflict",
    "current_revision": 4
  }
}
```

### Repository

Crear:

```text
backend/src/invoicing/draft_repository.py
backend/src/invoicing/draft_service.py
```

Evitar convertir `invoicing/service.py` en monolito.

## Autosave frontend

Crear:

```text
frontend/src/features/confirmation/useReviewDraft.ts
frontend/src/features/confirmation/useDraftAutosave.ts
```

State:

```ts
type DraftSaveState =
  | 'clean'
  | 'dirty'
  | 'saving'
  | 'saved'
  | 'save_error'
  | 'confirming'
```

Debounce:

```text
750 ms
```

### Confirm guard

No confirmar mientras:

```text
dirty || saving
```

Primero:

```text
final save
→ wait success
→ confirm
```

---

# 21. FASE 14 — REVIEW DATA Y CONFIRMACIÓN

## REQ R-023 — Review prioriza draft

`GET /uploads/{id}/review`:

```text
if draft exists
  → fields from draft
else
  → fields from OCR
```

Añadir:

```json
{
  "source": "draft",
  "draft_revision": 4,
  "draft_updated_at": "...",
  "page_count": 1
}
```

## REQ R-024 — Confirmación atómica

En `invoicing.service.confirm`:

```text
authorize
→ revalidate server-side
→ insert invoice
→ tax lines
→ correction diff
→ audit
→ update uploaded_file confirmed
→ delete review_draft
→ COMMIT
```

Ningún cleanup de MinIO antes del commit.

## REQ R-025 — Confirmar y siguiente

Frontend:

```text
confirm current
→ success
→ invalidate inbox
→ request current inbox snapshot
→ select first ready
→ navigate /confirmar/{next}
```

Si no:

```text
/mis-facturas
```

No seleccionar `next` antes del commit.

---

# 22. FASE 15 — VISOR DE DOCUMENTO EN REVIEW

Modificar `ConfirmationScreen.tsx`.

Desktop:

```text
┌──────────────────┬─────────────────────┐
│ documento        │ formulario          │
│ página 1/N       │ autosave status     │
│ zoom             │ campos              │
└──────────────────┴─────────────────────┘
```

Móvil:

```text
documento
↓
formulario
```

### Descarga de imagen

Usar endpoint autenticado.

```text
fetch → Blob → URL.createObjectURL
```

Cleanup:

```text
URL.revokeObjectURL
```

Headers:

```http
Cache-Control: private, no-store, max-age=0
Pragma: no-cache
X-Content-Type-Options: nosniff
```

Multipágina:

- lazy por página;
- `Página X / N`.

Miniaturas:

- toggle OFF por defecto;
- no descargar si está OFF.

---

# 23. FASE 16 — SUPERVISIÓN DE TENANT_ADMIN

## REQ R-026

Crear panel diferente de “Mis facturas”.

Ejemplo:

```text
/pendientes-equipo
```

Puede ver metadata:

- usuario;
- empresa;
- estado;
- fecha;
- dirección;
- páginas.

Puede abrir pendiente ajena:

```text
read-only
```

No mostrar:

- Guardar;
- Confirmar;
- Confirmar y siguiente.

### Regla crítica

`tenant_admin` poder administrar el tenant **no convierte al administrador en propietario del borrador**.

Una factura confirmada sí sigue el mecanismo administrativo actual de `PATCH /invoices/{id}`.

---

# 24. FASE 17 — ADMIN_TECH GLOBAL

## REQ R-027

Integrar en plataforma.

### Listado

Metadata global sin descargar automáticamente el documento.

### Apertura explícita

Solo `is_admin_tech`.

Cada apertura:

```text
admin_tech.pending_document.read
```

Audit:

```text
actor_user_id
tenant_id target
company_id
uploaded_file_id
timestamp
request_id
source_ip
```

No guardar OCR raw en el audit.

### Cross tenant

No ejecutar negocio con SQL libre desde `platform_session`.

Usar:

- función SECURITY DEFINER acotada, o;
- resolver tenant y abrir `tenant_session` explícita.

---

# 25. FASE 18 — RETENCIÓN 90 DÍAS

## REQ R-028

Job diario:

```text
purge_expired_unconfirmed_documents
```

Candidatos:

```sql
status <> 'confirmed'
AND created_at < now() - interval '90 days'
```

Orden:

```text
seleccionar
→ borrar relaciones provisionales/draft en DB
→ borrar upload/pages DB
→ audit sin PII
→ COMMIT
→ borrar objetos MinIO best-effort
```

### Métrica

```text
expired_pending_count
purge_storage_failures
```

No borrar antes el objeto si la DB todavía afirma que existe.

---

# 26. FASE 19 — CORRECCIÓN DEL LABORATORIO OCR

## REQ R-029 — Mistral estructurado real

Modificar:

```text
backend/src/ocr/engines/mistral_extractor.py
```

Eliminar la decisión:

```text
structured fields → always None
```

### Crear schema común primero

Ver R-031.

### Request conceptual

```python
response = await client.ocr.process_async(
    model=settings.mistral_ocr_model,
    document=document,
    include_image_base64=False,
    include_blocks=True,
    confidence_scores_granularity="block",
    document_annotation_format={
        "type": "json_schema",
        "json_schema": {
            "name": "invoice_extraction",
            "schema": InvoiceExtractionSchema.model_json_schema(),
        },
    },
    document_annotation_prompt=INVOICE_EXTRACTION_PROMPT,
)
```

**Ajustar a la firma exacta de la versión `mistralai` fijada en el proyecto antes de implementar.**

No adivinar campos del SDK.

### Amounts como string

Por interoperabilidad:

```json
"total_amount": "121.00"
```

no:

```json
"total_amount": 121.00
```

El parser convierte a `Decimal`.

## REQ R-030 — Gemini candidates

Modificar:

```text
backend/src/shared/config.py
.env.example
docs/...
```

No reemplazar un solo string por “latest”.

Añadir IDs explícitos:

```python
gemini_35_flash_model: str = "gemini-3.5-flash"
gemini_36_flash_model: str = "gemini-3.6-flash"
gemini_35_flash_lite_model: str = "gemini-3.5-flash-lite"
```

Producción apunta a una versión estable elegida manualmente.

---

# 27. FASE 20 — CONTRATO ESTRUCTURADO ÚNICO

## REQ R-031

Crear:

```text
backend/src/ocr/schema.py
```

Pydantic v2.

```python
from pydantic import BaseModel, Field

class TaxLineSchema(BaseModel):
    rate: str | None = None
    base: str | None = None
    quota: str | None = None

class TaxIdSchema(BaseModel):
    value: str | None = None
    name: str | None = None
    value_confidence: str | None = None
    name_confidence: str | None = None

class InvoiceExtractionSchema(BaseModel):
    schema_version: str = "1"
    issue_date: str | None = None
    invoice_number: str | None = None
    total_amount: str | None = None
    net_amount: str | None = None
    tax_amount: str | None = None
    irpf_rate: str | None = None
    irpf_amount: str | None = None
    tax_lines: list[TaxLineSchema] = Field(default_factory=list)
    tax_ids: list[TaxIdSchema] = Field(default_factory=list)
```

### Regla

El contrato no contiene objetos específicos de Gemini/Mistral.

Los adapters traducen proveedor → contrato.

### Confianza

La confianza **autodeclarada por el proveedor** nunca es suficiente para auto-confirmar por sí sola.

---

# 28. FASE 21 — BENCHMARK COMPARABLE Y PROMOCIÓN

## REQ R-032

El benchmark debe controlar:

```text
mismo documento
mismas páginas
misma variante
mismo schema
mismas normalizaciones
misma ground truth
mismos campos puntuables
```

### Candidatos mínimos

```text
Gemini 3.5 Flash
Gemini 3.6 Flash
Gemini 3.5 Flash-Lite
Mistral OCR 4.0 GA + annotation
```

Mistral OCR 4.1:

```text
laboratorio preview
```

hasta que sea GA o se acepte explícitamente riesgo preview.

### Métricas por engine/model/variant

- field exact accuracy;
- critical-field accuracy;
- all-critical-exact;
- tax-lines accuracy;
- arithmetic-valid-after-extraction;
- hallucination flags;
- p50;
- p95;
- errors;
- pages;
- API cost;
- manual corrections per invoice.

### Separación

No incluir un motor cuya salida estructurada se vacía artificialmente.

## Regla de promoción

Nunca:

```text
benchmark winner
→ auto switch production
```

Siempre:

```text
benchmark
→ review admin-tech
→ “Promover a producción”
→ audit
→ nueva policy_version
```

---

# 29. FASE 22 — POLÍTICA OCR DE PRODUCCIÓN

## REQ R-033 — Primario fijo

Crear:

```text
backend/src/ocr/policy.py
```

```python
class OcrPolicy(BaseModel):
    version: int
    primary_engine: str
    primary_model: str
    fallback_enabled: bool
    fallback_engine: str | None
    fallback_model: str | None
    consensus_mode: str
```

La política de producción debe ser independiente del laboratorio.

### Recomendación inicial

Hasta tener benchmark Autoken limpio:

```text
primario provisional: Gemini 3.5 Flash
challenger: Gemini 3.6 Flash
fallback candidate: Mistral OCR 4.0 GA
```

Esto no se codifica como verdad eterna.

## REQ R-034 — Fallback condicional

No ejecutar dos OCR siempre.

Disparadores:

```text
provider_timeout
provider_error
critical_field_missing
critical_field_low_confidence
counterparty_tax_id_invalid
invoice_math_mismatch
supplier_profile_conflict
hard_fail_but_image_quality_good
```

No disparar por:

```text
counterparty name confidence == media
```

si el resto es sólido; la propia App2 ya descubrió que forzar el nombre a alta confianza produce revisiones excesivas.

### Resultado fallback

Si corrige una duda:

```text
reconcile
```

Si aumenta conflicto:

```text
needs_review
```

No pedir automáticamente un tercer LLM solo para desempatar.

---

# 30. FASE 23 — CONSENSO POR CAMPO

## REQ R-035

Refactorizar/extender:

```text
backend/src/ocr/arbiter.py
```

El arbiter actual escoge por self-confidence.

Necesita:

```python
@dataclass(frozen=True)
class FieldCandidate:
    field: str
    normalized_value: str | None
    raw_value: object
    engine: str
    model: str
    provider_confidence: float | None
```

### Normalización por campo

Crear:

```text
backend/src/ocr/normalization.py
```

- NIF/CIF: mayúsculas, quitar espacios/guiones;
- fecha: ISO si parseable;
- amounts: Decimal canonical;
- invoice number: normalización conservadora; no borrar `/` o `-` indiscriminadamente;
- nombres: Unicode/whitespace para comparar, conservar original final.

### Regla de consenso

1. agrupar candidatos por valor normalizado;
2. sumar evidencia;
3. aplicar validadores deterministas;
4. aplicar supplier evidence;
5. elegir si el margen supera threshold;
6. si no, `unresolved`.

```python
class FieldDecision(BaseModel):
    value: object | None
    score: float
    status: Literal["accepted", "uncertain", "conflict"]
    sources: list[str]
    reasons: list[str]
```

No perder trazabilidad.

---

# 31. FASE 24 — SCORE DE CONFIANZA POR CAMPO

## REQ R-036

Separar:

```text
provider_confidence
```

de:

```text
system_confidence
```

### Evidencias

Sistema final puede considerar:

```text
+ provider confidence
+ agreement between independent engines
+ deterministic validation
+ supplier identity match
+ learned supplier pattern
+ image quality
- disagreement
- failed checksum
- arithmetic mismatch
- fallback-only field
```

### No hardcodear una fórmula “científica” sin calibrar

Implementar inicialmente un modelo de reglas explicable.

Ejemplo:

```python
def compute_field_confidence(e: Evidence) -> ConfidenceResult:
    score = 0.50

    if e.primary_high:
        score += 0.15
    if e.fallback_agrees:
        score += 0.20
    if e.deterministic_valid:
        score += 0.15
    if e.deterministic_invalid:
        score = min(score, 0.35)
    if e.engine_conflict:
        score -= 0.20

    return clamp(score)
```

Los coeficientes iniciales deben calibrarse contra correcciones humanas.

### Reason codes

Ejemplos:

```text
primary_high
engines_agree
tax_id_checksum_ok
tax_id_checksum_failed
invoice_math_ok
invoice_math_failed
supplier_known
supplier_pattern_match
supplier_pattern_conflict
image_low_quality
fallback_used
engines_disagree
```

Frontend puede explicar:

```text
“Confianza media: dos lecturas discrepan en el número de factura”
```

sin exponer nombres internos de proveedores IA al usuario final.

---

# 32. FASE 25 — VALIDACIÓN FISCAL / CHECKSUM

## REQ R-037

Preservar:

```text
backend/src/ocr/verification.py
backend/src/ocr/analysis.py
shared/tax_id.py
```

### Extender resultado

Hoy se devuelve un `CheckResult` global.

Añadir, sin romper contrato anterior, estructura detallada:

```python
class TaxLineCheck(BaseModel):
    index: int
    expected_quota: Decimal
    actual_quota: Decimal
    delta: Decimal
    valid: bool

class InvoiceMathCheck(BaseModel):
    line_checks: list[TaxLineCheck]
    expected_total: Decimal | None
    actual_total: Decimal | None
    total_delta: Decimal | None
    valid: bool | None
    reasons: list[str]
```

### IVA

El parser actual restringe demasiado pronto a:

```text
21 / 10 / 4 / 0
```

Para producción multicliente/histórico es más robusto:

1. extraer `rate` numérico finito si está impreso;
2. conservarlo;
3. marcar `unknown_tax_rate` si no corresponde a política conocida;
4. enviar a revisión;
5. nunca descartar silenciosamente el tramo porque el porcentaje no esté en una whitelist embebida.

La política fiscal por fecha/jurisdicción debe vivir separada del parser OCR.

---

# 33. FASE 26 — APRENDIZAJE POR PROVEEDOR

## REQ R-038

App2 ya tiene `counterparties`.

No copiar `known_cifs` de Setex literalmente.

Crear segundo nivel:

```text
supplier_profiles
```

scope:

```text
tenant_id
+ company_id
+ counterparty_cif_blind_index
```

### Motivo

Una misma asesoría puede gestionar múltiples empresas.

El mismo proveedor puede tener comportamientos distintos por empresa cliente:

- serie de factura;
- tramos habituales;
- retención;
- layout;
- textos.

### Esquema recomendado

```sql
supplier_profiles (
    id uuid PK,
    tenant_id uuid NOT NULL,
    company_id uuid NOT NULL,
    counterparty_cif_blind_index text NOT NULL,

    confirmations int NOT NULL DEFAULT 0,
    invoice_number_patterns jsonb NOT NULL DEFAULT '[]',
    tax_rate_histogram jsonb NOT NULL DEFAULT '{}',
    tax_line_count_histogram jsonb NOT NULL DEFAULT '{}',
    field_correction_stats jsonb NOT NULL DEFAULT '{}',
    last_seen_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    UNIQUE (tenant_id, company_id, counterparty_cif_blind_index)
)
```

No guardar el CIF en claro.

### Cómo aprende

Solo después de confirmación humana exitosa.

Hook:

```text
invoicing.service.confirm
→ transaction invoice succeeds
→ update supplier profile in same transaction
```

o, si el cálculo de patrones es caro:

```text
persist minimal counters transactionally
→ background derive patterns
```

### Cold start

```text
confirmations < 3
→ profile no influye en auto-decision
```

### Uso

El supplier profile:

- puede subir/bajar score;
- puede detectar anomalías;
- puede ayudar a fallback;
- puede sugerir nombre exacto desde `counterparties`.

No puede:

```text
“el proveedor siempre factura 21%”
→ sobrescribir una imagen que claramente dice 10%
```

### Few-shot de Setex

Setex planteaba inyectar ejemplos verificados del mismo proveedor en re-extracción.

Para Autoken:

- P2;
- solo fallback;
- seleccionar ejemplos sin PII cruzada;
- mismo tenant+company+counterparty;
- no meter factura anterior completa;
- construir features/patrones o ejemplo mínimo;
- nunca copiar valores históricos a la factura actual.

---

# 34. FASE 27 — TESSERACT COMO EVIDENCIA LOCAL

## REQ R-039

No meter Tesseract en el camino crítico inicialmente.

Experimento:

```text
backend/src/ocr/local_evidence/
  __init__.py
  tesseract_checker.py
```

### Función

```python
class LocalTextEvidence(BaseModel):
    available: bool
    matched_fields: dict[str, bool | None]
    duration_ms: int
```

Buscar de forma tolerante:

- CIF/NIF;
- número;
- total;
- fecha.

### Regla

Un “no encontrado” de Tesseract:

- no invalida automáticamente;
- reduce confianza como evidencia débil.

Un “encontrado”:

- suma evidencia.

### Ejecución

- proceso/worker separado si CPU significativa;
- paralelo o background;
- nunca añadir 5–6 segundos seriales a la UX.

---

# 35. FASE 28 — PADDLEOCR / SURYA COMO CHALLENGERS

## REQ R-041/R-042

No instalar dentro del contenedor API principal.

Crear interfaz:

```text
DocumentLayoutEngine
```

y, solo en entorno lab:

```text
ocr-layout-paddle service
ocr-layout-surya service
```

### Qué medir

No medir solo texto OCR.

Medir si layout mejora específicamente:

- tax lines;
- tablas;
- multi-column;
- asociación label/value;
- reading order;
- facturas complejas.

### Criterio de promoción

Solo considerar integración production si:

```text
critical-field accuracy gain >= umbral acordado
AND p95 acceptable
AND infra cost acceptable
AND ops complexity justified
```

Un +0.5% de accuracy no justifica una GPU y otro servicio si la corrección humana ya cuesta menos.

---

# 36. FASE 29 — COLAS Y PRIORIDADES

## REQ R-043 — Separar trabajo de usuario y laboratorio

Hoy los jobs comparten cola.

Crear settings:

```python
ocr_primary_queue_name: str = "autoken:queue:ocr:primary"
ocr_background_queue_name: str = "autoken:queue:ocr:background"
```

### Primary queue

- `run_ocr`;
- retry de usuario;
- recovery.

### Background queue

- comparison;
- ranking;
- benchmark;
- backfill;
- Tesseract shadow;
- layout challengers.

### Workers

```text
worker-primary
worker-background
```

El lab no puede ocupar todos los slots del usuario.

## REQ R-044 — `max_jobs`

En:

```text
backend/src/shared/config.py
```

```python
ocr_worker_max_jobs: int = 4
ocr_background_worker_max_jobs: int = 1
```

Mapear a ARQ:

```python
class WorkerSettings:
    max_jobs = settings.ocr_worker_max_jobs
```

`4` es punto inicial, no SLA.

Calibrar con:

- CPU;
- RAM;
- pool Postgres;
- rate limits proveedor;
- p95.

## REQ R-045 — Circuit breaker

Para caída de primario:

Redis state por:

```text
engine + model
```

Estados:

```text
closed
open
half_open
```

No crear fallback storm si primario falla 100 veces por outage.

### Ejemplo

```text
5 fallos retryable / 60 s
→ open 30 s
→ primary requests route to configured fallback
→ half-open probe
```

Debe ser configurable y testado con reloj falso.

---

# 37. FASE 30 — PRODUCCIÓN OCR VS LABORATORIO

## REQ R-046

El único booleano actual:

```text
ocr_experiment_enabled
```

es demasiado grueso.

Separar settings.

### Producción

```text
ocr_primary_engine
ocr_primary_model
ocr_fallback_enabled
ocr_fallback_engine
ocr_fallback_model
ocr_consensus_mode
ocr_policy_version
```

### Laboratorio

```text
ocr_lab_visible
ocr_auto_benchmark_enabled
ocr_benchmark_engines
ocr_benchmark_variants
```

### UI admin-tech

`PlatformSettings.tsx`:

```text
┌ Producción OCR ─────────────────┐
│ Primario: Gemini 3.5 Flash      │
│ Fallback: Mistral 4.0 [ON]      │
│ Política: v7                    │
└─────────────────────────────────┘

┌ Laboratorio ────────────────────┐
│ Ejecutar benchmark auto [OFF]   │
│ Modelos ...                     │
│ [Abrir laboratorio]             │
└─────────────────────────────────┘
```

### Botón solicitado

Debe existir:

```text
[ Desactivar laboratorio automático ]
```

Al apagar:

```text
zero auto benchmark calls
```

La producción continúa con el modelo fijo.

### Promoción

Botón:

```text
[ Promover esta combinación a producción ]
```

Requiere:

- confirm modal;
- old policy;
- new policy;
- actor;
- timestamp;
- audit.

---

# 38. FASE 31 — ETA Y TELEMETRÍA

## REQ R-047

Instrumentar sin PII:

```text
upload_to_201_seconds
ocr_queue_wait_seconds
ocr_processing_seconds
ocr_fallback_rate
ocr_fallback_seconds
ocr_failure_rate
draft_save_latency_seconds
draft_save_failures
review_duration_seconds
pending_count
ready_count
expired_pending_count
```

Tags permitidos:

- environment;
- engine;
- model;
- status;
- page_count bucket;
- tenant aggregate ID solo si la política de observabilidad lo permite y nunca PII.

No taggear:

- CIF;
- proveedor;
- invoice number;
- amount.

## REQ R-048 — ETA

No mostrar desde el día 1:

```text
“faltan 34 segundos”
```

sin base estadística.

### Requisito mínimo

```text
>= 30 completions
```

en ventana reciente para la combinación:

```text
engine/model/page_count bucket
```

### Fórmula de primera aproximación

```text
waves = ceil(pending_ahead / effective_concurrency)

ETA ≈ queue_wait_estimate
    + waves × rolling_p75_processing_seconds
```

En sesión de 10:

no usar simplemente:

```text
10 × media
```

si existen varios slots.

### UI

```text
“Aproximadamente 20–35 s”
```

preferible a precisión falsa.

Si muestra insuficiente:

```text
sin ETA numérica
```

---

# 39. FASE 32 — SEGURIDAD ESPECÍFICA DEL NUEVO FLUJO

## 39.1. Matriz

| Amenaza | Control obligatorio |
|---|---|
| UUID de upload ajeno | server reauthorization + RLS + owner guard |
| mismo tenant/empresa, otro usuario | SELF ONLY para inbox/draft |
| draft sobrescrito por otra pestaña | revision CAS + 409 |
| tenant_admin modifica pending ajena | endpoint read-only / guard |
| admin-tech modifica | no endpoint write |
| PII en inbox | DTO metadata-only |
| PII en logs | structured log allowlist |
| PII en browser cache | no-store + query cleanup logout |
| MinIO público | prohibido |
| XSS desde OCR | React escaping; no `dangerouslySetInnerHTML` |
| benchmark cross-tenant | tenant session + encryption |
| stale worker updates progress | claim token fencing |
| double capture | imperative capture lock |
| duplicate upload | existing private SHA constraint |
| malicious file | existing MIME/size/antivirus |
| queue Redis down | existing recoverable pending semantics |

## 39.2. Logout

Eliminar:

- inbox queries;
- review queries;
- blob URLs;
- document image cache;
- draft state;
- capture session state.

---

# 40. FASE 33 — ERRORES Y RETRIES

## Upload

Retryable manual:

```text
network
timeout
502
503
504
```

No auto-loop:

```text
400
401
403
404
409 business conflict
413
415
422
429
```

`429` debe mostrar una espera razonable si hay `Retry-After`.

## OCR

Mantener claim/recovery.

Proveedor retry/fallback:

- clasificar error;
- timeout configurable;
- no retry infinito;
- circuit breaker;
- final `ocr_failed` solo tras política agotada.

## `capture_unreadable`

Nueva captura:

```text
old unreadable
→ capture new
→ 201 new
→ entonces replacement/delete old
```

Nunca eliminar old antes de que new sea durable.

---

# 41. FASE 34 — FEATURE FLAGS Y ROLLOUT

Añadir, con ubicación consistente en settings de plataforma/config según alcance:

```text
scanner_v2_enabled
continuous_capture_enabled
review_inbox_enabled
draft_autosave_enabled
processing_stages_enabled
ocr_policy_v2_enabled
supplier_learning_enabled
```

### Orden de rollout

```text
1. tests/CI
2. local
3. staging
4. admin-tech / tenant interno
5. una asesoría piloto
6. dos asesorías piloto
7. 25%
8. 100%
```

No es obligatorio implementar porcentaje si el sistema actual no tiene targeting.

Puede usarse una allowlist temporal de tenant IDs en configuración de plataforma, sin exponerla al cliente.

### Rollback

Cada flag debe permitir volver al flujo anterior sin revertir migraciones compatibles.

---

# 42. PLAN DE CAMBIOS FICHERO POR FICHERO

## 42.1. Frontend

| Ruta | Cambio |
|---|---|
| `frontend/src/features/capture/types.ts` | CaptureProductMode, CaptureMode, normalized corners, quality |
| `capture/scannerConfig.ts` | NUEVO, parámetros calibrables |
| `capture/coordinates.ts` | NUEVO, object-cover transforms |
| `capture/DocumentOverlay.tsx` | NUEVO, SVG yellow polygon |
| `capture/scannerProtocol.ts` | NUEVO, messages worker |
| `capture/scanner.worker.ts` | NUEVO, OpenCV off-main-thread |
| `capture/useScannerEngine.ts` | NUEVO, lifecycle/requestId/in-flight |
| `capture/analyzeFrame.ts` | mover/adaptar a nuevo FrameAnalysis |
| `capture/opencv/documentEdges.ts` | candidate scoring/confidence |
| `capture/opencv/blur.ts` | ROI-based score |
| `capture/captureLoop.ts` | auto/manual state machine |
| `capture/processCapture.ts` | still redetection + conservative crop + natural filter |
| `capture/CapturePreview.tsx` | NUEVO, Repetir/Usar foto |
| `capture/CaptureScreen.tsx` | orquestar modos + stream persistente + no monolito |
| `capture/useUploadCapture.ts` | extraer pure transports; session metadata |
| `processing/ProcessingProgress.tsx` | NUEVO |
| `processing/progressModel.ts` | NUEVO mapping stage→UX |
| `inbox/InvoiceInbox.tsx` | NUEVO |
| `inbox/useInvoiceInbox.ts` | NUEVO aggregate polling |
| `confirmation/ConfirmationScreen.tsx` | split document/form + draft + confirm-next |
| `confirmation/useDraftAutosave.ts` | NUEVO |
| `confirmation/useReviewDraft.ts` | NUEVO |
| `app/routes.ts` | `/mis-facturas`, supervisión |
| `app/AppRoutes.tsx` | no navigate confirm on upload |
| `api/schema.d.ts` | regenerado, nunca manual |

## 42.2. Backend

| Ruta | Cambio |
|---|---|
| `backend/src/invoice_intake/constants.py` | preservar FileStatus |
| `invoice_intake/processing.py` | NUEVO ProcessingStage |
| `invoice_intake/models.py` | stage/timestamps/session fields |
| `invoice_intake/repository.py` | stage update fenced, inbox queries |
| `invoice_intake/service.py` | capture session validation; preserve intake invariants |
| `invoice_intake/router.py` | status DTO, capture session multipart |
| `invoicing/draft_repository.py` | NUEVO |
| `invoicing/draft_service.py` | NUEVO |
| `invoicing/router.py` | draft endpoint / review extension |
| `invoicing/service.py` | confirm deletes draft + supplier hook |
| `jobs/ocr.py` | stage instrumentation + OCR policy/fallback |
| `jobs/queue.py` | primary/background queues |
| `jobs/worker.py` | max_jobs config / primary worker |
| `jobs/background_worker.py` | NUEVO si se separa proceso |
| `ocr/schema.py` | NUEVO provider-neutral Pydantic schema |
| `ocr/policy.py` | NUEVO |
| `ocr/normalization.py` | NUEVO |
| `ocr/arbiter.py` | evidence-based field consensus |
| `ocr/analysis.py` | consume system confidence + detailed validation |
| `ocr/verification.py` | granular diagnostics |
| `ocr/extraction_json.py` | compatibility parser + remove premature tax-rate loss |
| `ocr/engines/gemini_extractor.py` | schema-native output/versioned models |
| `ocr/engines/mistral_extractor.py` | structured annotation real |
| `ocr/ranking_engines.py` | new candidates/fair registration |
| `counterparty/models.py` | preserve counterparty master |
| `counterparty/service.py` | preserve record_confirmation |
| `supplier_intelligence/models.py` | NUEVO profile model |
| `supplier_intelligence/repository.py` | NUEVO |
| `supplier_intelligence/service.py` | NUEVO |
| `platform_admin/settings_*` | production/lab split |
| `shared/config.py` | queue names, models, max_jobs |
| `.env.example` | config keys, no secrets |
| OpenAPI | regenerate |

## 42.3. Migraciones propuestas

Sujetas a `alembic heads`.

```text
0041_capture_session_progress.py
0042_review_drafts.py
0043_pending_inbox_index.py
0044_ocr_policy_settings.py
0045_supplier_profiles.py
```

No agrupar todo en una migración gigante.

---

# 43. CONTRATOS API PROPUESTOS

## 43.1. Upload single/continuous

```http
POST /api/v1/uploads
Content-Type: multipart/form-data

file
company_id?
direction
sharpness?
capture_session_id?
capture_sequence?
```

201:

```json
{
  "id": "uuid",
  "status": "pending_ocr"
}
```

## 43.2. Multipage

Se mantiene:

```http
POST /api/v1/uploads/batch
```

Semántica:

> una factura, varias hojas.

## 43.3. Status

```http
GET /api/v1/uploads/{id}/status
```

## 43.4. Inbox personal

```http
GET /api/v1/invoices/inbox?cursor=...
```

## 43.5. Draft

```http
PUT /api/v1/uploads/{id}/draft
```

## 43.6. Review

```http
GET /api/v1/uploads/{id}/review
```

## 43.7. Confirm

Se preserva:

```http
POST /api/v1/uploads/{id}/confirm
```

## 43.8. Supervision tenant

Ejemplo:

```http
GET /api/v1/invoices/pending-supervision
GET /api/v1/uploads/{id}/review-readonly
```

No reutilizar un endpoint write con “readonly=true”.

---

# 44. MATRIZ DE ORIGEN DE MEJORAS

| Mejora | Origen principal | Decisión |
|---|---|---|
| claim/lease/fencing/recovery | App2 | preservar |
| RLS + MinIO privado + antivirus | App2 | preservar |
| checksum fiscal/Decimal | App2 | preservar/extender |
| supplier master tenant | App2 | preservar |
| OpenCV detector/warp | App2 | extender |
| field arbiter | App2 | extender |
| benchmark real | App2 | corregir |
| proveedor aprendido | Setex | adaptar a tenant+company |
| Tesseract anti-alucinación | Setex | P2 background |
| CLAHE benchmark | Setex | lab, no default |
| calidad calibrada con facturas reales | Setex | portar metodología |
| modelos configurables/hot-swap | Setex | adaptar a policy admin-tech |
| Single/Multiple/Combine | Dext | adoptar patrón |
| auto capture + margin + blur | Veryfi | adoptar patrón |
| glare/LCD detection | Veryfi | P2 |
| auto boundary/perspective | ABBYY | patrón ya alineado |
| structured JSON native | Gemini/Mistral | P0 |
| layout/table service | Paddle/Surya | P3 challenger |
| Sauvola/Niblack | scikit-image | laboratorio |

---

# 45. COSTE/BENEFICIO DE LAS MEJORAS

| Mejora | Coste impl. | Beneficio | Veredicto |
|---|---|---|---|
| Preview obligatoria | Bajo | Muy alto | Hacer ya |
| No navegar a confirm tras upload | Bajo | Muy alto | Hacer ya |
| Captura continua | Medio | Muy alto | Hacer ya |
| Barra por stages reales | Medio | Alto | Hacer ya |
| Inbox personal | Medio/alto | Muy alto | Hacer ya |
| Draft autosave | Alto | Muy alto | Hacer ya |
| Scanner candidate scoring | Alto | Alto | Hacer antes de auto-capture |
| Web Worker scanner | Alto | Alto en móviles | Hacer P1 |
| Auto capture | Medio después del gate | Alto | Hacer |
| Mistral adapter correcto | Medio | Muy alto para decidir proveedor | Bloqueante lab |
| Gemini 3.5/3.6 benchmark | Bajo/medio | Muy alto | Bloqueante lab |
| Fallback condicional | Alto | Muy alto | Hacer tras bench |
| Consenso por campo | Alto | Muy alto | Hacer tras fallback |
| Supplier profiles | Alto | Alto creciente | Hacer P1 |
| Tesseract verifier | Medio | Incierto | P2 benchmark |
| Paddle/Surya | Muy alto | Incierto | P3 |
| scikit-image runtime | Medio | Bajo vs OpenCV | No |
| jscanify runtime | Medio | Bajo porque ya hay OpenCV | No |
| Glare/LCD | Alto | Medio | P2 |
| WebSockets | Medio | Bajo ahora | No inicial |
| IndexedDB/background sync | Alto | Bajo con política online | No inicial |

---

# 46. PLAN DE TESTS TRAZABLE

## 46.1. Scanner unit

```text
coordinates.test.ts
qualityGate.test.ts
documentEdges.test.ts
captureLoop.test.ts
progressModel.test.ts
```

Casos:

- object-cover portrait/landscape;
- corners normalizados round-trip;
- object at edge clipped;
- blur;
- dark;
- bright;
- perspective extreme;
- moving;
- stable;
- AUTO captures;
- MANUAL always captures;
- AUTO→MANUAL cancels armed;
- no double capture.

## 46.2. Scanner integration

- camera permission denied;
- torch unsupported;
- Worker unsupported fallback;
- worker error;
- stale requestId;
- retake does zero HTTP;
- use photo sends one HTTP;
- 201 resumes camera;
- duplicate response;
- 413;
- offline;
- iOS fallback.

## 46.3. Continuous

- 10 accepted → 10 file IDs;
- sequence order;
- stream persists;
- #3 upload failure does not lose #1/#2;
- #3 must resolve before #4 under wait-for-201 policy;
- OCR for #1 can finish while #7 being captured.

## 46.4. Progress

- pending = En cola;
- processing + each stage;
- fallback branch;
- error branch;
- stage never decreases visually;
- old backend no stage = indeterminate;
- user cannot query other's progress.

## 46.5. Inbox security

Scenario:

```text
Tenant A
Company X
Alice
Bob
```

- Alice upload visible to Alice;
- Bob same company → not visible;
- Bob guessed UUID → 404;
- tenant_admin “Mis facturas” → only own;
- tenant_admin supervision → Alice metadata;
- tenant_admin opens Alice → read-only;
- tenant B → no access.

## 46.6. Drafts

- lazy create;
- debounce;
- revision N→N+1;
- stale revision →409;
- close/reopen keeps draft;
- encrypted columns not plaintext;
- owner-only write;
- tenant_admin cannot write other's;
- admin-tech cannot write;
- confirm deletes draft.

## 46.7. OCR schema

Para cada engine:

- valid schema;
- nullable;
- malformed JSON;
- unexpected field;
- decimal string;
- multi-tax-line;
- no tax;
- IRPF;
- unsupported rate retained and flagged;
- prompt injection printed on invoice.

## 46.8. Mistral correction

Test must fail if extractor deliberately returns empty despite valid annotation payload.

Fixtures:

```text
annotation with CIF/date/total
→ ExtractedInvoice populated
```

## 46.9. Fallback

- primary success high → exactly 1 provider call;
- primary timeout → fallback 1 call;
- primary missing total → fallback;
- invalid CIF → fallback;
- math mismatch → fallback;
- fallback agrees → score up;
- fallback disagrees → needs_review;
- circuit open → skip primary;
- no fallback configured → review/fail per policy.

## 46.10. Supplier learning

- 1 confirmation: does not auto-influence;
- 3 confirmations: evidence active;
- same provider different company: separate profile;
- same provider different tenant: separate;
- contradictory current invoice: profile cannot overwrite;
- human correction updates stats.

## 46.11. Load

Escenario mínimo:

```text
10 usuarios
× 10 facturas
= 100 uploads
```

Medir:

- upload p50/p95;
- queue wait;
- OCR p50/p95;
- DB pool;
- Redis;
- worker saturation;
- provider 429;
- recovery;
- zero cross-user data leak.

---

# 47. SLO / OBJETIVOS OPERATIVOS PROPUESTOS

No son compromisos contractuales iniciales.

| Métrica | Objetivo inicial |
|---|---:|
| upload→201 p95, red razonable | ≤ 3 s |
| inbox refleja 201 | ≤ 2 s con pantalla abierta |
| OCR final reflejado tras commit | ≤ 2 s por polling |
| autosave p95 | ≤ 1 s backend, excluido debounce |
| draft error silencioso | 0 |
| cross-tenant leak | 0 |
| duplicate double capture | 0 |
| benchmark provider calls con lab OFF | 0 |
| primary provider calls por invoice normal | 1 |
| fallback rate | medir; no fijar antes de benchmark |

### Gatillo background upload

Si:

```text
upload→201 p95 > 2–3 s
```

de forma habitual en móviles reales:

activar fase futura:

```text
CaptureUploadGateMode = background_upload
```

Pero no implementar IndexedDB/outbox ahora.

---

# 48. PRUEBAS EN DISPOSITIVOS REALES

Obligatorias:

- Android gama media + Chrome;
- Android PWA instalada;
- iPhone Safari;
- iPhone PWA;
- orientación portrait;
- poca luz;
- luz lateral;
- sombra;
- mesa clara;
- mesa oscura;
- factura arrugada;
- A4;
- ticket estrecho;
- impresión tenue;
- factura con varias bases IVA;
- factura con IRPF.

Medir:

- FPS aparente;
- tiempo análisis;
- CPU/temperatura;
- falsos AUTO;
- tiempo a stable;
- crop correcto;
- legibilidad OCR.

Un detector que obtiene buen score desktop pero congela un Android medio no está terminado.

---

# 49. DEFINITION OF DONE — ESCENARIO E2E

## Escenario principal

Alice abre “Varias facturas”.

1. AUTO está activo.
2. Encuadra factura #1.
3. polígono amarillo sigue el papel.
4. calidad llega a ready.
5. captura AUTO.
6. se procesa automáticamente.
7. preview.
8. Alice pulsa `Usar foto`.
9. UI muestra `Guardando factura…`.
10. backend responde 201.
11. UI muestra `✓ Guardada`.
12. cámara sigue abierta.
13. factura #1 aparece `En cola`.
14. Alice captura #2…#8.
15. #1 y #2 ya pueden estar “Lista para revisar” antes de acabar #8.
16. termina captura.
17. abre `/mis-facturas`.
18. ve solo sus ocho documentos.
19. los processing muestran barra real:
    - Verificando;
    - Procesando;
    - Comprobando;
    - Casi está.
20. abre una lista.
21. corrige.
22. 750ms → autosave.
23. cierra PWA.
24. reabre.
25. cambios siguen.
26. confirma.
27. se crea `invoice`.
28. se borra `review_draft`.
29. upload pasa `confirmed`.
30. desaparece de inbox.
31. se abre siguiente ready.

## Seguridad paralela

Bob, misma Company:

- no ve documentos de Alice;
- UUID de Alice → 404.

Tenant admin:

- en Mis facturas ve solo propias;
- en Supervisión ve metadata de Alice;
- abre Alice read-only;
- no confirma.

Admin-tech:

- metadata global;
- abrir exige acción explícita;
- se audita;
- read-only.

## Retención

Documento sin confirmar >90d:

- purge DB;
- commit;
- cleanup MinIO;
- audit sin PII.

---

# 50. DEFINITION OF DONE — OCR

No se considera terminada la nueva política OCR hasta que:

1. Mistral tenga extracción estructurada real.
2. Gemini stable candidates estén configurados.
3. todos compartan schema canónico.
4. benchmark use ground truth humana.
5. exista informe field-by-field.
6. producción tenga primary fijo.
7. lab pueda apagarse sin afectar producción.
8. fallback solo se ejecute bajo trigger.
9. llamadas proveedor sean contabilizables.
10. consensus deje reason codes.
11. validaciones fiscales se integren.
12. supplier learning no cruce company/tenant.
13. benchmark lab OFF produzca cero llamadas experimentales.
14. ningún modelo pueda auto-promocionarse.

---

# 51. COSAS QUE EXPLÍCITAMENTE NO DEBEN IMPLEMENTARSE AHORA

```text
❌ OCR inline HTTP
❌ 2–6 motores en todas las facturas
❌ árbitro LLM siempre bloqueante
❌ jscanify como segundo pipeline OpenCV duplicado
❌ scikit-image dentro del runtime web/backend
❌ Paddle/Surya en el mismo proceso FastAPI
❌ WebSockets solo para sustituir polling de 2 s
❌ IndexedDB de facturas sin conexión
❌ Background Sync antes de medir upload→201
❌ editor manual de esquinas
❌ URLs públicas MinIO
❌ tabla pending_invoices redundante
❌ auto-switch de modelo según último benchmark
❌ aprender proveedor a través de tenants
❌ sobreescribir OCR actual por patrón histórico
❌ porcentajes de progreso basados solo en temporizador
```

---

# 52. ORDEN EXACTO DE IMPLEMENTACIÓN RECOMENDADO

## Bloque A — Correcciones sin gran riesgo

1. baseline.
2. crear spec.
3. separar modos de captura.
4. refactor `useUploadCapture`.
5. preview Repetir/Usar.
6. quitar navegación automática a confirm.
7. continuous wait-for-201.
8. mantener camera stream.
9. tests.

## Bloque B — Progreso e inbox

10. migración session/progress.
11. ProcessingStage.
12. instrument `jobs/ocr.py`.
13. status DTO.
14. ProcessingProgress.
15. inbox repository/service/router.
16. `/mis-facturas`.
17. tests RLS/owner.

## Bloque C — Draft/review

18. migration draft.
19. RLS.
20. draft service.
21. autosave.
22. review source draft.
23. confirm delete draft.
24. confirm-next.
25. visor documento.
26. tests security/concurrency.

## Bloque D — Scanner v2

27. normalized coordinates.
28. candidate score.
29. quality gate.
30. overlay.
31. AUTO/MANUAL reducer.
32. still redetection.
33. natural filter.
34. worker off-main-thread.
35. device testing.
36. calibrate thresholds.

> El Web Worker puede desarrollarse antes, pero funcionalmente AUTO no debe abrirse a usuarios hasta que candidate score y quality gate estén validados.

## Bloque E — OCR correctness

37. `InvoiceExtractionSchema`.
38. Mistral structured annotations.
39. Gemini 3.5/3.6/Lite adapters.
40. fair benchmark.
41. elegir primary provisional.
42. production policy settings.
43. lab split.
44. background queue split.

## Bloque F — OCR adaptativo

45. fallback.
46. consensus.
47. confidence fusion.
48. detailed fiscal checks.
49. circuit breaker.
50. load tests.

## Bloque G — Learning

51. supplier_profiles.
52. update after human confirm.
53. evidence integration.
54. correction statistics.
55. calibration.

## Bloque H — Opcionales medidos

56. Tesseract lab.
57. CLAHE/Sauvola benchmark.
58. glare detector.
59. Paddle challenger.
60. Surya challenger.
61. numeric ETA.

---

# 53. INSTRUCCIONES PARA EL AGENTE QUE IMPLEMENTE ESTA SPEC

El agente debe:

1. leer el fichero objetivo completo antes de modificarlo;
2. inspeccionar tests existentes de esa feature;
3. comprobar migración head real;
4. hacer cambios pequeños y trazables;
5. añadir tests antes de dar una tarea por cerrada;
6. ejecutar typecheck/test/build;
7. no “limpiar” código ajeno a la tarea;
8. no modificar contratos de seguridad para facilitar tests;
9. no inventar fields de SDKs externos;
10. consultar versión instalada del SDK antes de usar una firma;
11. mantener DTOs sin PII por defecto;
12. regenerar OpenAPI/types si cambia API;
13. documentar feature flag/rollback;
14. medir antes de optimizar;
15. no activar una feature experimental automáticamente.

## Plantilla de cierre por requerimiento

```markdown
### R-XXX — Cierre

- Implementado:
- Archivos cambiados:
- Migración:
- Tests unitarios:
- Tests integración:
- Prueba manual:
- Métricas:
- Riesgos restantes:
- Feature flag:
- Rollback:
- Evidencia:
```

Un requisito no está resuelto porque “el código compila”.

Está resuelto cuando sus criterios observables pasan.

---

# 54. TRAZABILIDAD A LAS DOS ESPECIFICACIONES APORTADAS

## Escáner documental

Se incorporan:

- AUTO default;
- MANUAL siempre;
- detección continua;
- polígono;
- object-cover mapping;
- normalized corners;
- 4–5 análisis/s;
- preview 720px;
- worker;
- one-in-flight;
- candidate scoring;
- quality gate;
- ROI sharpness;
- exposure;
- perspective;
- stability;
- double-capture lock;
- contextual messages;
- HD still;
- redetection;
- document filtering;
- device tests;
- OCR benchmark.

Se sustituye:

```text
manual corner editor
```

por:

```text
automatic still redetection
+ conservative crop/full-image fallback
+ mandatory visual preview
```

porque la spec posterior lo cierra.

## Captura continua / drafts

Se incorporan:

- 5–10;
- wait 201;
- no offline;
- async OCR;
- provisional uploaded_files vs invoices;
- existing FileStatus;
- review_drafts;
- encrypted PII;
- RLS;
- 750ms autosave;
- revision;
- draft-first review;
- atomic confirm;
- confirm-next;
- personal inbox;
- no PII list;
- aggregate polling;
- cursor;
- tenant supervision;
- admin-tech audited read;
- no-store image;
- multipage;
- thumbnails OFF;
- unreadable safe replacement;
- 90d purge;
- current rate limit;
- claim/lease/fencing/recovery;
- configurable concurrency;
- priority for user OCR;
- capture state machine;
- future upload gate flag;
- no IndexedDB initial.

---

# 55. FUENTES DE INVESTIGACIÓN EXTERNA USADAS PARA DECIDIR

Consultar de nuevo antes de implementar integraciones de terceros, porque las APIs cambian.

## Captura / mercado

- Dext Help — mobile capture modes:
  `https://help.dext.com/en/articles/105670-how-to-scan-and-upload-documents-in-the-dext-mobile-app`
- Veryfi Lens Browser docs:
  `https://docs.veryfi.com/lens/browser-v2/getting-started/introduction/`
- Veryfi configuration:
  `https://docs.veryfi.com/lens/browser-v2/advanced/configuration/`
- ABBYY Mobile Web Capture product material:
  `https://www.abbyy.com/`

## OCR

- Gemini 3.5 Flash:
  `https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash`
- Gemini 3.6 Flash:
  `https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash`
- Gemini structured output:
  `https://ai.google.dev/gemini-api/docs/structured-output`
- Mistral OCR endpoint:
  `https://docs.mistral.ai/api/endpoint/ocr`
- Mistral annotations:
  `https://docs.mistral.ai/studio/document-processing/annotations`

## Open source / document processing

- PaddleOCR PP-StructureV3:
  `https://www.paddleocr.ai/main/en/version3.x/algorithm/PP-StructureV3/PP-StructureV3.html`
- Surya:
  `https://github.com/datalab-to/surya`
- Tesseract:
  `https://github.com/tesseract-ocr/tesseract`
- jscanify:
  `https://github.com/puffinsoft/jscanify`
- scikit-image exposure/CLAHE:
  `https://scikit-image.org/docs/stable/api/skimage.exposure.html`
- scikit-image Sauvola:
  `https://scikit-image.org/docs/stable/auto_examples/segmentation/plot_niblack_sauvola.html`

---

# 56. DECISIÓN FINAL DE ARQUITECTURA

El sistema definitivo no será:

```text
foto
→ 6 IAs
→ esperar
→ revisar
```

Será:

```text
ESCÁNER INTELIGENTE
→ mejor input posible

INTAKE DURABLE
→ 201 rápido y seguro

COLA PRIMARIA
→ usuario no bloqueado

MOTOR PRIMARIO FIJO
→ una llamada normal

VALIDACIÓN DETERMINISTA
→ CIF + matemáticas

FALLBACK SOLO SI HACE FALTA
→ segunda evidencia

CONSENSO EXPLICABLE
→ score por campo + razones

APRENDIZAJE POR PROVEEDOR
→ mejora progresiva sin cruzar tenants

BANDEJA + AUTOSAVE
→ revisión eficiente por lotes

CONFIRMACIÓN HUMANA
→ invoice definitiva

LABORATORIO AISLADO
→ innovación sin penalizar producción
```

Ese es el objetivo de producción de Autoken Facturas / Autofactu.

---

# 57. CHECKLIST FINAL DE ACEPTACIÓN GLOBAL

- [ ] rama/head verificados
- [ ] specs precedencia documentada
- [ ] no manual corner editor
- [ ] Single/Continuous/Multipage separados
- [ ] AUTO default
- [ ] MANUAL siempre disponible
- [ ] yellow overlay
- [ ] candidate score
- [ ] quality gate
- [ ] stability
- [ ] HD redetection
- [ ] preview mandatory
- [ ] wait 201
- [ ] stream retained
- [ ] 10 independent invoices supported
- [ ] progress stages durable/fenced
- [ ] “Verificando / Procesando / Casi está”
- [ ] `/mis-facturas` self-only
- [ ] aggregated polling
- [ ] drafts encrypted + RLS
- [ ] autosave 750ms + revision
- [ ] confirm atomic
- [ ] confirm-next
- [ ] tenant-admin read-only supervision
- [ ] admin-tech audited read
- [ ] 90-day purge
- [ ] Mistral benchmark corrected
- [ ] Gemini stable candidates benchmarked
- [ ] common structured schema
- [ ] production primary fixed
- [ ] lab can be OFF with zero calls
- [ ] fallback conditional
- [ ] consensus field-level
- [ ] deterministic fiscal checks preserved
- [ ] supplier profile company-scoped
- [ ] primary/background queues separated
- [ ] worker concurrency configurable
- [ ] circuit breaker tested
- [ ] PII not logged
- [ ] MinIO private
- [ ] IDOR/RLS tests
- [ ] 100-upload load test
- [ ] Android real test
- [ ] iPhone real test
- [ ] rollback documented
- [ ] OpenAPI/types regenerated
- [ ] production canary completed

---


# 58. MATRIZ MAESTRA DE VERIFICACIÓN — REQUISITO → EVIDENCIA

Esta tabla es normativa. Un agente no puede marcar un requisito como completado sin producir la evidencia indicada.

| ID | Evidencia mínima de cierre |
|---|---|
| R-000 | SHA de `develop`, `alembic heads/current`, pytest, frontend typecheck/test/build verdes |
| R-001 | spec de precedencia versionada + test/ausencia de cualquier `DocumentCropEditor` productivo |
| R-002 | test UI/API demuestra 3 modos y que continuous crea N IDs, multipage 1 ID |
| R-003 | typecheck + unit tests de NormalizedCorners/config sin números mágicos fuera de config |
| R-004 | test prueba `maxInFlight===1`, frames intermedios descartados y stale `requestId` ignorado |
| R-005 | fixtures de detector muestran candidate score y `confidence∈[0,1]`; regresiones de contornos |
| R-006 | `qualityGate.test.ts` cubre cada reason y es función pura sin DOM/OpenCV |
| R-007 | reducer tests AUTO default, MANUAL fallback, reset al toggle, lock evita doble capture |
| R-008 | screenshot/E2E móvil demuestra polígono mapeado correctamente con `object-cover` |
| R-009 | test still HD no reutiliza blindly preview corners; fallback conserva imagen si geometry dudosa |
| R-010 | test `Repetir` hace 0 HTTP; `Usar foto` hace exactamente 1 upload; no editor de esquinas |
| R-011 | integration test upload resuelve al `201`; OCR no forma parte de duración HTTP |
| R-012 | E2E captura 10: cada 201 habilita siguiente y OCR anteriores corre simultáneamente |
| R-013 | migración + ORM + index + query de session ordered; session metadata no cambia autorización |
| R-014 | route test: upload success no navega `/confirmar/:id` |
| R-015 | mock MediaStream demuestra que no se solicita un nuevo stream tras cada 201 en continuous |
| R-016 | migración añade stage/timestamps; FileStatus enum permanece sin estados duplicados |
| R-017 | worker tests demuestran secuencia de stages y que claim token antiguo no puede actualizar |
| R-018 | unit mapping stage→texto/% + a11y role + fallback indeterminate sin stage |
| R-019 | endpoint/status e inbox devuelven metadata sin PII; una sola query polling por inbox |
| R-020 | Alice ve sus uploads; Bob misma empresa no; tenant_admin en “Mis” sigue self-only |
| R-021 | pg inspection muestra CIF/nombre draft cifrados; RLS FORCE; foreign key cascade |
| R-022 | debounce 750ms; CAS revision; test stale revision→409; draft sobrevive reload |
| R-023 | review sin draft→OCR; con draft→draft; devuelve source/revision/timestamp |
| R-024 | test transaccional: invoice+tax+audit+confirmed+delete draft juntos; rollback deja todo intacto |
| R-025 | E2E confirm current→commit→invalidate→next ready; no next→`/mis-facturas` |
| R-026 | tenant_admin puede leer pending ajena pero todos los endpoints de escritura responden deny |
| R-027 | admin-tech sin flag→403; con flag apertura explícita crea audit; no write path |
| R-028 | reloj congelado >90d: DB purge commit y MinIO cleanup; fallo MinIO no revive DB |
| R-029 | fixture Mistral annotation rellena campos; benchmark deja de puntuar por `None` artificial |
| R-030 | registry contiene stable 3.5/3.6/Lite; production no usa alias `latest`; smoke configurable |
| R-031 | schema JSON idéntico/compatible en adapters; amounts strings→Decimal; schema_version presente |
| R-032 | benchmark report incluye mismo corpus/variant/schema + field accuracy/p95/error/cost por motor |
| R-033 | policy persisted/versioned; production worker usa exactamente primary configurado |
| R-034 | primary high→1 llamada; triggers definidos→fallback; no second call en happy path |
| R-035 | fixtures agreement/disagreement por campo; conflict sin margen→needs_review |
| R-036 | cada field decision incluye numeric score + reasons + sources; deterministic invalid cap probado |
| R-037 | fixtures multi-IVA/IRPF/rounding; detailed deltas; tax rate desconocido se conserva+revisión |
| R-038 | profile separado tenant/company; <3 confirmations no influye; current contradiction no override |
| R-039 | benchmark shadow mide precisión/latencia/CPU; flag OFF implica cero ejecución |
| R-040 | reporte offline compara raw/natural/CLAHE/Gray/Sauvola con mismo ground truth |
| R-041 | Paddle corre solo en servicio/lab; API principal no importa Paddle; benchmark documentado |
| R-042 | Surya corre solo en servicio/lab; API principal no importa torch/Surya; benchmark documentado |
| R-043 | primary jobs y benchmark aparecen en colas Redis diferentes; saturar background no retrasa primary test |
| R-044 | `max_jobs` proviene de Settings; load test justifica valor productivo |
| R-045 | test reloj simula open/half-open/closed; outage no genera tormenta de llamadas |
| R-046 | UI separa Producción/Lab; apagar auto-lab→0 provider calls experimentales y production sigue |
| R-047 | dashboard/log metrics muestra upload/queue/OCR/draft/review sin labels PII |
| R-048 | con n<30 no hay ETA; con n>=30 cálculo usa p75/concurrencia y rango aproximado |
| R-049 | suite IDOR/RLS/cache/log/minio pasa; búsqueda de logs de test no encuentra PII fixtures |
| R-050 | escenario 100 uploads completa; reporta p50/p95/pool/Redis/429/recovery; 0 leaks |
| R-051 | canary documentado; flags permiten rollback funcional sin downgrade destructivo |
| R-052 | confirmación sin salto automático; pendientes borrables; duplicados exactos/fiscales bloqueados; latencia de captura medida sin PII |
| R-053 | contenido autenticado crema/claro; barra superior y cámara conservan contraste oscuro; funciones y permisos sin cambios |

## 58.1. Evidencia que debe quedar en el repositorio

Por cada bloque implementado, guardar cuando proceda:

```text
docs/evidence/
  scanner-v2/
  continuous-capture/
  progress/
  inbox-drafts/
  ocr-benchmark/
  ocr-policy/
  supplier-learning/
  load/
```

No guardar facturas reales ni PII.

Artefactos permitidos:

- JSON de métricas anonimizadas;
- tablas CSV sin PII;
- screenshots con datos sintéticos;
- output de tests;
- `EXPLAIN ANALYZE` con datos sintéticos;
- benchmark IDs anonimizados;
- policy versions.

## 58.2. Regla “no hay Done por impresión visual”

No son evidencia suficiente:

```text
“parece funcionar”
“el spinner se ve bien”
“Gemini parece acertar más”
“el worker no dio error en mi prueba”
“con 2 facturas fue rápido”
```

Se exige el criterio medible del ID correspondiente.


**FIN DE LA ESPECIFICACIÓN MAESTRA**

# ADR-0016: Worker OCR con motor único (gemini-3-flash a JSON) y árbitro por campo con N=1

- **Estado**: aceptado
- **Fecha**: 2026-07-11
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: ADR-0003 (pipeline OCR de 4 capas), ADR-0007 (gemini-3-flash como motor de lectura),
  ADR-0010 (verificación "tipo DNI"), ADR-0001 (RLS de dos niveles), ADR-0015 (object storage/intake),
  spec `docs/specs/S2.3-worker-ocr.md`, PLAN MAESTRO §11.8; tarea S2.3

## Contexto
Una factura subida (S2.1, en `pending_ocr`) debe convertirse en **campos estructurados fiables** antes
de que un humano los confirme (S2.4). El worker lee la imagen/PDF con IA, extrae los **campos de oro**
(fecha, importes y, sobre todo, el **CIF de la contraparte**), aplica **validaciones deterministas**
(mód-23 del CIF, cuadre aritmético) y decide si la factura va directa a confirmación (`auto_ok`) o a
**revisión reforzada** (`needs_review`). La regla dura e innegociable (regla de oro 4): un campo que no
se lee con seguridad se queda en `null` con aviso; **jamás un valor inventado llega a la pantalla**.

El pipeline de lectura del plan (ADR-0003) contempla **N motores en paralelo** con un **árbitro** que
reconcilia sus lecturas por campo. El bench de Fase 1 (ADR-0007) eligió **gemini-3-flash** como motor
de lectura. Queda decidir con cuántos motores arranca S2.3 y cómo se estructura el árbitro.

## Decisión

### 1. Motor único: gemini-3-flash prompteado a JSON estructurado
S2.3 arranca con **un solo motor**, gemini-3-flash, pero **prompteado para devolver JSON estructurado**
(los campos de oro con una confianza por campo `alta`/`media`/`baja` y `null` cuando el dato no es
legible), no una transcripción libre a Markdown como en la capa de bench (`ocr/engines`). El extractor
es una abstracción inyectable (`ocr.extraction.InvoiceExtractor`): los tests inyectan un doble y el
motor real solo se ejerce en integración/staging (coste, credenciales, red); **nunca en CI**. Cualquier
fallo del proveedor se traduce a `InvoiceExtractionError` y deja el fichero en `ocr_failed`, sin
extracción parcial.

### 2. Árbitro por campo, pero con N=1 (identidad)
El árbitro (`ocr.arbiter.reconcile`) se implementa **por campo** desde el primer día, pero hoy corre con
**N=1**, así que es la identidad sobre la única lectura. Los extractores se lanzan con `asyncio.gather`
(hoy una sola coroutine). El diseño por campo permite **añadir un segundo motor sin reescribir** el job:
basta ampliar la estrategia de selección por campo. Se separa en su módulo (no acoplado al job) para
que N>1 no exija tocar el cableado de I/O.

### 3. Segundo motor diferido
El **segundo motor y su árbitro real** se añadirán cuando la calidad del CIF de contraparte lo exija
(es el campo que más falla). No entra en S2.3.

### 4. Contraparte = el identificador que no es el CIF propio
El CIF/nombre **propios** se **conocen** desde `companies` y se inyectan; NO se leen ni se puntúan. La
**contraparte** es el identificador fiscal leído cuyo valor normalizado (`shared.tax_id.normalize_tax_id`)
NO es el propio (el de mayor confianza si hay varios); `null` si no hay ninguno. Que el CIF propio
aparezca en la factura es un control anti-foto-equivocada (`own_tax_id_present`): si no aparece,
`needs_review`. La dirección emisor/receptor (S2.2/S2.4) no es necesaria aquí.

### 5. Solo validación L1
Aquí solo se hace **L1** del CIF de contraparte (estructura/mód-23, `shared.tax_id.validate_tax_id`) y el
**cuadre aritmético** de tramos+total (`ocr.verification.check_invoice_totals`, con tolerancia de
redondeo para no generar falsos descuadres). L2-L4 (supplier master, AEAT/VIES/BORME, caché) son S2.8.
Las validaciones **marcan, no corrigen**: nunca alteran el valor leído.

## Alternativas consideradas
- **Arrancar ya con N>1 motores + árbitro real**: más robustez en el CIF de contraparte, pero duplica
  coste/latencia y complejidad del árbitro sin datos de producción que guíen la política de fusión. Se
  difiere hasta que el CIF de contraparte lo exija.
- **Reutilizar la transcripción a Markdown del bench y parsear el texto**: frágil (regex sobre prosa) y
  propenso a alucinación; el JSON estructurado con confianzas por campo es determinista de parsear.
- **Persistir la identidad propia leída por OCR**: contradice la enmienda §11.8 (la identidad propia se
  conoce, no se lee); un nombre propio mal leído no debe enrutar a revisión.

## Consecuencias
- **Positivas**: anti-alucinación garantizada (campo no legible = `null` + aviso); enrutado por
  confianza claro (`auto_ok`/`needs_review`); coste/latencia mínimos con N=1; camino de crecimiento a
  N>1 sin reescritura; aislamiento por RLS de dos niveles en `ocr_extractions` (anti-cruce de tenants);
  idempotencia del reprocesado (upsert por `uploaded_file_id`).
- **Negativas / deuda asumida**: con N=1 no hay contraste entre motores para el CIF de contraparte (se
  compensa con L1 mód-23 y, más adelante, L2-L4 en S2.8); el árbitro por campo con N=1 es código
  "de más" hoy, justificado por evitar la reescritura al añadir el segundo motor.
- **Infra**: worker `arq` (cola Redis) desplegado como servicio aparte que comparte Postgres/Redis/MinIO;
  la API encola `run_ocr` best-effort tras cada subida aceptada (si el worker no está, el fichero se
  queda en `pending_ocr`, reintentable). `arq` declara `redis<6` pero opera con el redis 8 de la app;
  se instala en la imagen con `--no-deps` para no degradar redis (ver `pyproject.toml` extra `worker`).
  La compatibilidad arq/redis 8 se verifica en CI con un smoke test (`tests/test_ocr_worker_wiring.py`).
- **Guardarraíl de aislamiento**: el worker aplica el mismo control de arranque que la API (ADR-0014,
  `assert_runtime_role_cannot_bypass_rls`) vía `on_startup`: es un proceso que ESCRIBE fijando el
  contexto de tenant desde un mensaje encolado, así que un `DATABASE_URL` con privilegios elevados sería
  igual de grave que en la API y aborta el arranque (fail-loud). Grant a nivel de columna
  `UPDATE (status) ON uploaded_files`: el rol runtime solo mueve el estado, no reescribe `sha256`/
  `storage_key` (preserva el append-only del intake). `ocr_extractions.created_at` es inmutable
  (reprocesar refresca `updated_at`, no miente la creación).

## Notas de alcance y seguridad

### `auto_ok` NO salta la confirmación humana de S2.4
`auto_ok` significa "todos los campos de oro se leyeron con confianza alta y las validaciones L1
(mód-23 + cuadre) pasaron", NO "la factura es correcta y puede contabilizarse sin mirar". Mientras no
exista la **corroboración externa L2/L3 del CIF de contraparte** (supplier master + AEAT/VIES/BORME,
tarea **S2.8**), el CIF de contraparte solo tiene validación estructural: un CIF con mód-23 válido puede
seguir siendo de otra empresa. Por eso **`auto_ok` nunca omite el gate humano de confirmación de S2.4**;
solo distingue "candidata a confirmación directa" de "revisión reforzada". La decisión contable siempre
pasa por una persona hasta que S2.8 aporte la corroboración externa (regla de oro 4, anti-alucinación).

### C8 — "contradicción del CIF propio" ≡ "el CIF propio no aparece" (hoy)
La spec (§4/§5) menciona marcar una "contradicción" si el CIF propio leído no casa con el conocido. En
S2.3 la identidad propia se **conoce** (se inyecta desde `companies`) y se identifica en la factura solo
por **coincidencia** con ese CIF conocido; no hay dirección emisor/receptor (el selector Recibida/Emitida
es **S2.2**, diferida). Por tanto, "el CIF propio leído contradice el conocido" es **indistinguible** de
"el CIF propio conocido no aparece entre los leídos": ambos casos son `own_tax_id_present = false` y van
a `needs_review` (anti-foto-equivocada). No se implementa una señal de "contradicción" separada porque
no es determinable sin la dirección; esa distinción fina se difiere a **S2.4**. Es una alineación de la
documentación con lo implementado, no un cambio de comportamiento.

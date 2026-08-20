# PROMPT — Construir una "Vista OCR" + "Laboratorio de motores" para un pipeline de extracción documental con IA

> Copia todo este documento como prompt a la IA que deba implementarlo.
> Está escrito como **especificación ejecutable**: cada sección dice *qué* construir, *cómo*, y *por qué* (los "por qué" son lecciones aprendidas en producción; ignorarlas reintroduce bugs reales ya pagados).

---

## 0. ROL Y ENCARGO

Actúa como ingeniero full-stack senior especializado en pipelines de IA documental y en paneles de observabilidad para modelos.

Tienes que construir **dos herramientas de administración** sobre un sistema ya existente que extrae campos estructurados de documentos mediante varios motores de IA (OCR/visión/LLM):

1. **Vista de auditoría por documento** ("Vista OCR — Comparador IA vs Humano"): para *un* documento concreto, muestra qué leyó cada motor, qué decidió el sistema, qué confirmó el humano, y dónde falló.
2. **Laboratorio de motores** ("Benchmark"): ejecuta *N variantes de preprocesado de imagen × M motores* sobre documentos ya confirmados, puntúa cada combinación contra la verdad humana, y presenta un ranking con tres visualizaciones (barras, mapa de calor, líneas) y un desglose por grupo de campo.

**Objetivo de negocio de ambas:** dejar de decidir por intuición qué motor/preprocesado usar, y poder responder con datos a "¿qué combinación acierta más en NIF? ¿y en fechas? ¿y en importes?".

---

## 1. RESTRICCIONES DE STACK (adáptalas a tu proyecto, pero respeta el espíritu)

- Frontend: **JavaScript vanilla ES6+, sin framework ni bundler**. Única dependencia de tabla: Tabulator (vendorizada localmente). Los gráficos se dibujan **a mano con CSS y SVG inline** — no añadir librerías de charts.
- Backend: Node.js + Express, PostgreSQL.
- Sin `onclick` inline en el HTML: hay CSP estricta. Todos los handlers con `addEventListener`.
- Todo el HTML generado desde JS pasa por un escapador (`escHtml` / `escAttr`). Los datos vienen de OCR de documentos subidos por terceros: **son entrada no confiable, XSS real si no se escapa**.

---

## 2. MODELO CONCEPTUAL — LAS TRES COLUMNAS HONESTAS

Este es el concepto central de la Vista de auditoría. Impleméntalo exactamente.

Un valor extraído atraviesa tres estados, y confundirlos hace que el panel mienta:

| Columna | Nombre | Qué contiene |
|---|---|---|
| **1** | `ia_pura` — "Leyó la IA" | Fusión de los motores + recálculos aritméticos del orquestador. **Antes** de tocar la base de datos. |
| **2** | `ocr_raw` — "Decidió el sistema" | Lo anterior, **más** las sobrescrituras desde catálogos internos (maestro de entidades conocidas, relaciones aprendidas, registro del propio usuario). Es exactamente lo que se le presentó al humano para confirmar. |
| **3** | `confirmed` — "Confirmado humano" | Lo que hay hoy en la BD, incluidas las ediciones manuales posteriores desde el panel. |

**Por qué importa (bug real):** al principio solo existían dos columnas y se llamaba "IA" a la columna 2. El panel afirmaba que "la IA acertó" valores que la IA **nunca había leído** — los había puesto el catálogo interno. La métrica de precisión del OCR estaba inflada y las decisiones sobre qué motor usar se tomaban sobre un dato falso.

**Regla de acierto:** el badge "¿Acertó el sistema?" compara **columna 2 contra columna 3**, no la 1 contra la 3.
- Rationale: la 2-vs-3 mide *lo que de verdad llega al usuario final*, que es lo que importa para el producto. La 1-vs-3 mide la precisión del motor aislado — útil, pero es otra pregunta, y se responde con la columna 1 + el ranking por motor.
- Beneficio adicional: la columna 1 no existe en documentos anteriores a que se empezara a persistir `ia_pura`. Si el badge dependiera de ella, todo el histórico saldría "n/d". Con 2-vs-3 el badge está disponible en **todos** los documentos.

Añade un campo `overrides_bd: [{campo, fuente, valor_ia}]` que explique campo a campo la diferencia entre columnas 1 y 2, y píntalo como un **badge marrón con `title` mostrando lo que había leído la IA**.

---

## 3. CONTRATO DEL ENDPOINT DE AUDITORÍA

`GET /api/admin/documentos/:id/ocr-detail` → solo administradores técnicos (ver §8).

```jsonc
{
  "confirmed": { /* todos los campos escalares + array de tramos/desglose */ },

  "ia_pura":  { /* idem, o null en documentos antiguos */ },
  "ocr_raw":  { /* idem — nombre de clave heredado, es la columna 2 */ },
  "overrides_bd": [ { "campo": "receptor_nif", "fuente": "registro_usuario", "valor_ia": "B1234567" } ],

  // Qué leyó CADA motor que participó de verdad en este documento.
  // Construir dinámicamente, NUNCA hardcodear la lista de motores.
  "motors": {
    "<slot>": { "engine": "<nombre real del motor>", "campos": { /* ... */ } }
  },

  // Qué motor aportó cada campo final. Etiquetar EXPLÍCITAMENTE a qué columna describe.
  "campo_sources": { "total": "consensus", "fecha_emision": "azure", "...": "..." },
  "campo_sources_describe": "ia_pura",

  "meta": {
    "dual_confirmed": true, "confidence_level": "alta",
    "iva_validation_ok": true, "iva_warnings": [],
    "ocr_engine": "openai+azure", "nif_status": null, "nif_discrepancy": null
  },

  "imagen_variante": {           // null si no se generó
    "motor": "openai",
    "campos_variante": { /* ... */ },
    "diffs": [ { "campo": "total", "original": "44,08", "variante": "44,80" } ]
  }
}
```

**Dos errores a no repetir:**
- `motors` estuvo hardcodeado a tres motores fijos, y una de las claves **nunca existió** en el JSON almacenado: era una lectura muerta que pintaba una columna siempre vacía. Constrúyelo iterando lo que de verdad hay en el resultado guardado (`extra_results[]` incluido), y expón `engine` con el **nombre real del motor**, no la clave del *slot* que lo alojó.
- `campo_sources` describe la columna 1, no la 2. Sin la etiqueta `campo_sources_describe`, el frontend lo pintaba junto a la columna equivocada y parecía desfasado.

---

## 4. VISTA DE AUDITORÍA — ESPECIFICACIÓN DE UI

Modal (overlay, `width:min(860px,96vw)`, `max-height:90vh`, scroll interno). Cierre por botón ✕ y por clic en el backdrop (`if (e.target === modal)`).

### 4.1 Tabla principal — 5 columnas

`Campo | 1 · Leyó la IA | 2 · Decidió el sistema | 3 · Confirmado humano | ¿Acertó el sistema?`

- Una fila por campo escalar de la lista `CAMPOS` (etiqueta legible + clave + formateador opcional).
- Badge de acierto: `✓✓` verde (`#276749`) si coinciden, `✗` rojo (`#9b2335`) si no, `—` gris si no es comparable (algún lado nulo).
- Fila con fondo `#fff5f5` cuando hay discrepancia — el ojo va solo a lo que falla.
- Columna 1: valor + **badge de color del motor** que lo aportó. Columna 2: valor + **badge marrón de origen** si fue sobrescrito.
- Debajo, un párrafo de leyenda que explique las tres columnas y el criterio de acierto **en lenguaje de negocio**. No es decorativo: sin él, cada persona interpreta el panel a su manera.

### 4.2 Normalización para comparar — el detalle que más bugs causó

Implementa **una sola** función de comparación y **compártela entre frontend y backend**:

```js
function normCmp(v) {
  if (v == null) return null;
  const s = String(v).trim().toUpperCase();
  // "1.234,56" -> 1234.56 ; "21" y "21,0" -> "21"
  const num = parseFloat(s.replace(/\.(?=\d{3}\b)/g, '').replace(',', '.'));
  if (!isNaN(num) && /^-?[\d.,]+$/.test(s)) return String(num);
  return s;
}
```

- **Los números se comparan por VALOR, no por texto.** `"21"` y `"21,0"` son el mismo porcentaje; se pintaban en rojo como discrepancia.
- **Mayúsculas en ambos lados.** Hubo un periodo en que el panel de auditoría normalizaba a mayúsculas y el del laboratorio no: la misma pareja de valores salía verde en un panel y roja en el otro. Un único criterio de acierto en todo el proyecto, importado desde un módulo común.
- **Nunca `parseFloat` ingenuo sobre importes con formato europeo.** `parseFloat("1.234,56")` devuelve `1.23`. Usa un parser de importes que entienda el separador de miles.

Para **importes** dentro de estructuras repetidas (tramos de IVA, líneas), compara con **tolerancia relativa del 2 %**; el porcentaje/tipo debe coincidir de forma **exacta**:

```js
function tramoNumMatch(a, b) {
  const fa = parseFloat(String(a).replace(',', '.')), fb = parseFloat(String(b).replace(',', '.'));
  if (isNaN(fa) || isNaN(fb)) return false;
  const max = Math.max(Math.abs(fa), Math.abs(fb));
  return max === 0 ? true : Math.abs(fa - fb) / max < 0.02;
}
```

### 4.3 Fila especial para estructuras repetidas

Los arrays anidados (tramos de IVA) no encajan en el bucle de campos escalares. Añádelos como **fila manual**, y compara serializando **solo los subcampos relevantes** (excluye ruido como descripciones de producto, que varían sin ser un error):

```js
JSON.stringify(normLineasCmp(raw)) === JSON.stringify(normLineasCmp(confirmed))
```

Si la tabla principal tiene una fila manual, **replícala también en el ranking por motor**. Bug real: el ranking iteraba solo la lista de campos escalares y a nadie se le ocurrió que la fila añadida a mano en la otra tabla faltaba aquí. Los datos ya estaban disponibles.

### 4.4 Ranking por motor dentro del documento

Tabla `Campo × Motor`, más una columna final `Confirmado` con fondo destacado.

- Celda verde `#f0fff4` si el motor coincide con lo confirmado; roja `#fff5f5` si discrepa; sin color si no es comparable.
- Encabezado de cada motor con **badge de color propio y consistente** en toda la app:

```js
const MOTOR_COLOR = {
  consensus: '#276749', openai: '#2b6cb0', azure: '#553c9a',
  gemini_flash: '#c05621', gemini_pro: '#b83280', mistral: '#9b2335',
  calculated: '#718096',
};
```

- Cuando el valor final vino de **consenso**, el badge debe nombrar **qué motores coincidieron**: `consenso: OpenAI + Azure DI`. Se calcula filtrando los motores cuyo valor normalizado iguala el valor final.
- Para la fila de estructuras repetidas no hay escalar que comparar: cuenta **cuántos tramos confirmados reportó cada motor** (`n/total`), con verde si todos, ámbar `#975a16` si algunos, rojo si ninguno. Y marca explícitamente cuando el motor **inventa** tramos que nadie confirmó: `(+2 no confirmados)` — es la señal de alucinación más directa que da el panel.

### 4.5 Comparativa visual de preprocesado

Si el documento se procesó con variante de imagen, muestra **original vs variante lado a lado** + tabla de campos donde difieren.

Las imágenes van tras autenticación, así que un `<img src="url">` normal **no** lleva el header. Cárgalas por `fetch` → `blob` → `URL.createObjectURL`:

```js
authFetch(url, { cache: 'no-store' })      // ← 'no-store' NO es opcional
  .then(r => r.ok ? r.blob() : Promise.reject(new Error(r.status === 404 ? 'no disponible' : `HTTP ${r.status}`)))
  .then(b => { img.src = URL.createObjectURL(b); })
  .catch(err => img.replaceWith(/* placeholder "Imagen no disponible (motivo)" */));
```

**Por qué `cache: 'no-store'`:** un `Ctrl+Shift+R` en la página **no** invalida la caché HTTP de un `fetch()` lanzado después al abrir el modal. Sin esto, un 404 servido antes de que la variante existiera queda cacheado indefinidamente para esa URL exacta (que no lleva cache-buster) y el usuario no tiene forma de forzar una petición nueva desde la propia página.

---

## 5. LABORATORIO / BENCHMARK — MOTOR DE EJECUCIÓN

### 5.1 Diseño

`V variantes de preprocesado × M motores` sobre un documento **ya confirmado por un humano**, puntuando cada combinación contra esa verdad.

Variantes de imagen de referencia:
- `actual` — la misma optimización que usa el pipeline de producción (p. ej. 1536 px máx, JPEG 85 %). Sirve para comparar motores *en igualdad de condiciones con lo que reciben normalmente*.
- `original` — el fichero tal cual se subió, sin reducir píxeles.
- `contraste` — contraste local adaptativo (CLAHE) + ajustes mínimos de brillo/saturación, generada **a partir de la original, no de la ya reducida**. CLAHE penaliza mucho menos las sombras que un contraste global simple — decisivo en fotos de móvil.

Si el fichero no es imagen (PDF), las 3 "variantes" son el mismo buffer: el benchmark sigue siendo comparable motor a motor aunque el eje de imagen no aporte nada en ese caso. **No lo trates como error.**

### 5.2 Reglas de ejecución no negociables

- **Es caro y no forma parte del producto.** `3 × 5 = 15 llamadas reales a APIs de pago por documento`. Que quede escrito en el propio módulo.
- **Nunca toca ni sustituye el pipeline real.** Es código aparte, en su propio fichero.
- Corre **solo bajo activación explícita**: un flag de configuración o un botón del panel.
- `ejecutarMotor()` **nunca lanza**: captura el error y lo devuelve como `{ error, tiempo_ms, campos: {} }`. Un motor caído no debe abortar el benchmark de los otros cuatro.
- Paraleliza **dentro** de cada variante (`Promise.allSettled` sobre los motores), y **secuencia** las variantes. Así el pico de concurrencia es M, no V×M.
- El lote retroactivo procesa **un documento detrás de otro**, no los 10 a la vez: 10 documentos × 15 llamadas simultáneas satura las APIs externas y dispara los 429.

### 5.3 Puntuación

```js
const CAMPOS_PUNTUABLES = [/* los campos clave del dominio */];

const GRUPOS_CAMPOS = {           // agrupación semántica para el desglose
  proveedor_nif: 'CIF/NIF',  receptor_nif: 'CIF/NIF',
  proveedor_nombre: 'Nombre', receptor_nombre: 'Nombre',
  numero_factura: 'Nº factura', fecha_emision: 'Fecha',
  total: 'Importes', base_imponible: 'Importes', cuota_iva: 'Importes',
  iva_porcentaje: 'Tramos IVA',
};

function puntuarContraConfirmado(campos, confirmado) {
  let aciertos = 0, comparables = 0; const detalle = {};
  for (const campo of CAMPOS_PUNTUABLES) {
    const vConf = confirmado[campo];
    if (vConf == null || vConf === '') continue;   // sin referencia → NO puntúa
    comparables++;
    const acierto = normCmp(campos[campo]) === normCmp(vConf);
    if (acierto) aciertos++;
    detalle[campo] = acierto;                       // ← clave para el desglose por grupo
  }
  return { aciertos, comparables, detalle };
}
```

**Los dos puntos que hacen que esto sirva:**
- **Un campo sin valor confirmado no puntúa** — ni a favor ni en contra. Si no, los motores parecen mejores o peores según cuántos campos rellenó el humano.
- **`detalle` guarda acierto/fallo POR CAMPO.** Es lo que permite construir después el ranking por grupo (¿falla más en CIF? ¿en fechas?) **sin volver a llamar a ninguna IA**. Sin `detalle` solo tienes un ratio agregado y hay que repetir (y repagar) todo el benchmark para responder la siguiente pregunta.

### 5.4 Persistencia

```sql
CREATE TABLE ocr_benchmark_resultados (
  id                SERIAL PRIMARY KEY,
  upload_id         INTEGER NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
  variante          VARCHAR(20) NOT NULL,
  motor             VARCHAR(30) NOT NULL,
  campos            JSONB   NOT NULL DEFAULT '{}',
  es_factura_valida BOOLEAN,
  tiempo_ms         INTEGER,
  error             TEXT,
  aciertos          INTEGER NOT NULL DEFAULT 0,
  comparables       INTEGER NOT NULL DEFAULT 0,
  detalle_campos    JSONB   NOT NULL DEFAULT '{}',
  creado_en         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX idx_benchmark_unico  ON ocr_benchmark_resultados (upload_id, variante, motor);
CREATE INDEX        idx_benchmark_upload ON ocr_benchmark_resultados (upload_id);
```

El índice único + `INSERT ... ON CONFLICT (upload_id, variante, motor) DO UPDATE SET ..., creado_en = NOW()` hace la reejecución **idempotente**: relanzar el benchmark actualiza en vez de duplicar filas y falsear los agregados.

Guarda `campos` completos aunque hoy no los pintes: son el material para responder preguntas futuras sin repagar las llamadas.

---

## 6. LABORATORIO — ENDPOINTS

| Método | Ruta | Función |
|---|---|---|
| `GET`  | `/admin/benchmark-flag` | Estado del flag de ejecución automática |
| `POST` | `/admin/benchmark-flag` | Activar/desactivar (valida `typeof enabled === 'boolean'`, escribe en config y **audita el cambio**) |
| `POST` | `/admin/documentos/benchmark/ultimas` | Dispara lote retroactivo sobre las últimas N |
| `GET`  | `/admin/documentos/benchmark/estado` | Progreso del lote en curso |
| `GET`  | `/admin/documentos/benchmark` | Filas crudas para la tabla de detalle |
| `GET`  | `/admin/documentos/benchmark/ranking` | Agregado por combinación motor×variante |

### 6.1 Candado de lote concurrente — obligatorio

```js
let benchmarkLoteEnCurso = null;   // null | { total, completadas, iniciadoEn }

// en POST /benchmark/ultimas:
if (benchmarkLoteEnCurso) {
  return res.status(409).json({
    error: `Ya hay un lote en curso (${benchmarkLoteEnCurso.completadas}/${benchmarkLoteEnCurso.total}) — espera a que termine.`,
  });
}
```

**Incidente real:** el botón no daba ninguna señal de progreso. El administrador lo pulsó dos veces (doble clic), ambas ejecuciones corrieron en paralelo sobre los mismos documentos y **duplicaron el gasto real en APIs de pago sin ningún beneficio**. El candado y el indicador de progreso nacieron de ahí. Implementa los dos: el candado sin feedback no arregla la causa, y el feedback sin candado no arregla el síntoma.

El endpoint **responde de inmediato** (`{ success, iniciado, documentos: N }`) y procesa en segundo plano. El contador `completadas` se incrementa en un `finally` — un documento que falle también avanza el progreso, si no la barra se queda clavada para siempre.

### 6.2 Guardas del lote

- `limit` con tope duro: `Math.min(parseInt(req.body?.limit,10) || 10, 30)`.
- **Path traversal:** `path.resolve(file_path)` y verificar `startsWith('/ruta/permitida/')` antes de leer. Descarta y loguea si no cumple. Es un fichero cuyo path viene de BD, pero la defensa en profundidad no se negocia.
- `await fs.access(safePath)` — el fichero puede haberse borrado desde que se registró.
- `try/catch` **por documento**, no solo global: un documento roto no puede matar el lote entero.

### 6.3 Agregación del ranking (sin llamar a ninguna IA)

Agrupa por `motor__variante` y acumula: `ejecuciones`, `errores`, `tiempoTotalMs/tiempoMuestras`, `aciertos`, `comparables`, y `grupos[grupo] = {aciertos, comparables}` recorriendo `detalle_campos` y mapeando cada campo por `GRUPOS_CAMPOS`.

Devuelve, ordenado por `ratio_global` descendente:

```jsonc
{
  "ranking": [{
    "motor": "openai", "variante": "contraste",
    "ejecuciones": 29, "errores": 0, "tiempo_medio_s": 4.31,
    "ratio_global": 94.4, "aciertos": 134, "comparables": 142,
    "por_grupo": [ { "grupo": "CIF/NIF", "ratio": 96.5, "aciertos": 55, "comparables": 57 } ]
  }],
  "total_filas": 435
}
```

**Toda la agregación es sobre datos ya almacenados.** Cambiar la pregunta no debe costar dinero.

---

## 7. LABORATORIO — UI

Modal grande: `width:min(1700px,98vw)`, `height:94vh`, layout **flex en columna** con `overflow:hidden` en el body y `flex:1; min-height:0` en la vista activa. En móvil (`max-width:768px`) pasa a pantalla completa sin bordes.

Dos pestañas: **📊 Ranking profesional** y **📋 Detalle por documento**.

### 7.1 Tarjetas "mejor combinación por variable" — siempre visibles

Encima de todo, una tarjeta por grupo de campo con **qué combinación motor+variante gana en ESE campo concreto** (no el ranking global). Borde izquierdo y píldora de porcentaje coloreados con el gradiente de §7.3.

Es la respuesta directa a la pregunta que motiva todo el laboratorio: *"dime la mejor combinación de modelo + forma de imagen para cada variable"*. No la escondas detrás de un filtro.

### 7.2 Chips de filtro

Grupos: `Vista` (barras / mapa de calor / líneas), `Motor` (Todos + cada uno), `Variante` (Todas + cada una), `Campo` (Global + cada grupo).

Regla de coherencia: **el mapa de calor ignora a propósito los chips de motor/variante** (es la vista "quiero verlo todo"), así que **ocúltalos** cuando esté activo y muestra en su lugar el chip de campo + una nota explicando por qué. Un filtro visible que no hace nada es peor que no tener filtro.

### 7.3 Escala de color continua — una sola función para todo

```js
function benchmarkColorGradiente(ratio) {
  if (ratio == null) return '#e2e8f0';
  const c = Math.max(0, Math.min(100, ratio));
  const hue = (c / 100) * 120;        // 0 = rojo, 60 = amarillo, 120 = verde
  const luz = 42 + (c / 100) * 8;     // ligeramente más claro cuanto mejor
  return `hsl(${hue}, 68%, ${luz}%)`;
}
```

Gradiente **continuo**, no bandas planas: la diferencia entre 71 % y 79 % se ve. Texto blanco con `text-shadow: 0 1px 3px rgba(0,0,0,.4)` para mantener contraste sobre todo el rango.

### 7.4 Las tres vistas

**Barras** (CSS puro). Una columna por grupo de campo, altura `%` = ratio con mínimo del 2 % (una barra de 0 % invisible parece un fallo de render). Etiqueta con `grupo` + `(aciertos/comparables)` — el ratio sin el tamaño de muestra es engañoso. Umbrales de color: `≥85` verde, `≥60` ámbar, resto rojo.

**Mapa de calor** (CSS grid/flex). Filas = motores, columnas = variantes, celda coloreada por `benchmarkColorGradiente`. Cada celda muestra el `%` grande, un subtexto `N documentos · N err.`, y un `title` completo al pasar el ratón. Efecto hover `transform: scale(1.07)` con sombra. Debajo, leyenda de la escala `0% ——— 100%` con el mismo gradiente en CSS.

**Líneas** (SVG inline, sin librería). Eje X = los grupos de campo en orden fijo, eje Y = 0-100 %, una `<polyline>` por motor con color propio + `<circle>` en cada punto con `<title>` para tooltip nativo. Rejilla horizontal en 0/25/50/75/100. Etiquetas del eje X truncadas a 9 caracteres + `…`.

```js
const ancho = 640, alto = 200, padIzq = 34, padDer = 12, padSup = 12, padInf = 30;
const posX = i => padIzq + (i / (cats.length - 1)) * (ancho - padIzq - padDer);
const posY = p => padSup + altoUtil - (Math.max(0, Math.min(100, p ?? 0)) / 100) * altoUtil;
// <svg viewBox="0 0 640 200" preserveAspectRatio="xMidYMid meet"> → responsive gratis
```

Las tres vistas comparten el mismo contenedor `#benchmark-chart`; el layout específico de cada una vive en su propio wrapper para que una no rompa a las otras.

### 7.5 Tabla de ranking (Tabulator)

Columnas: `# | Motor | Variante | % global | <una columna por grupo de campo> | Ejecuciones | Errores | Tiempo medio`. Fila 1 con fondo verde claro. `placeholder` que **diga qué hacer** cuando no hay datos: `"Sin datos todavía — activa el benchmark o pulsa Últimas 10"`.

Al refrescar, `replaceData(rows)` si la tabla ya existe; **no** la reconstruyas: se pierden orden y scroll del usuario.

### 7.6 Tabla de detalle por documento

Agrupada por documento (`groupBy: 'upload_id'`), con cabecera de grupo mostrando proveedor, fecha, total y nº de combinaciones.

**El "ganador" se calcula por documento, en ratio relativo** (mayor `aciertos/comparables` dentro de ese documento), no por recuento absoluto entre documentos: cada documento tiene distinto número de campos comparables y el recuento absoluto premia a los documentos más completos. Fila ganadora en verde, fila con error en rojo.

### 7.7 Progreso del lote

Poll cada 4 s con `setTimeout` (no `setInterval`: si una respuesta tarda, `setInterval` encola peticiones). Limpia el timer previo en cada entrada a la función.

Estados del botón: `▶ Últimas 10` → `Iniciando…` → `Procesando… (3/10)` → vuelta al inicial + refresco automático de la tabla al terminar. Texto de estado que gestione la expectativa: *"...puedes dejar el panel abierto o cerrarlo, seguirá en segundo plano"*.

Al abrir el modal, consulta el estado: si ya hay un lote corriendo, engánchate al progreso en vez de invitar a pulsar otra vez. Y si el `POST` devuelve **409**, no lo trates como error: muestra el mensaje y engánchate al lote existente.

Para el toggle de ejecución automática, **revierte el estado visual del checkbox si el guardado falla** — si no, la UI miente sobre una configuración que cuesta dinero.

---

## 8. SEGURIDAD Y COSTE — INNEGOCIABLE

- **Doble puerta de autorización.** No basta con `requireAdmin`: estas vistas exponen datos crudos de IA y **gastan dinero real**. Añade un segundo nivel (`isTechAdmin`) contra una lista explícita en configuración, verificada **en cada endpoint** del servidor. El ocultar botones en el frontend es cosmético, nunca control de acceso.
- Mutaciones (`POST`) protegidas además con anti-CSRF y comprobación de petición XHR.
- **Escapa todo lo que venga del OCR** antes de inyectarlo en HTML, incluidos los `title=""` (usa un escapador de atributos distinto del de contenido).
- Secretos de las APIs leídos de secretos montados en runtime con *fallback* a variables de entorno. **Nunca** hardcodeados ni en el repositorio.
- Cada cambio de flag que active gasto queda en el log de auditoría con usuario e IP.
- Toda combinación que gaste dinero deja traza en el log con su resultado: `[Benchmark] contraste/openai: 9/10 campos correctos`.

---

## 9. CRITERIOS DE ACEPTACIÓN

Entrega funcional cuando:

1. La vista de auditoría muestra las tres columnas correctamente diferenciadas y el badge compara 2-vs-3.
2. Un valor sobrescrito por catálogo interno **nunca** se contabiliza como acierto de la IA, y su badge de origen revela al pasar el ratón qué había leído la IA.
3. La misma pareja de valores da el **mismo** veredicto en la vista de auditoría y en el laboratorio (función de comparación compartida).
4. `"21"` vs `"21,0"` sale verde; `"1.234,56"` se muestra como `1.234,56 €` y no como `1,23 €`.
5. El ranking por motor incluye las estructuras repetidas con conteo `n/total` y marca los elementos inventados.
6. Doble clic en "Ejecutar" produce un 409 y **una sola** tanda de llamadas de pago.
7. Un motor que falla no impide que los demás completen; su error aparece en la fila correspondiente.
8. Reejecutar el benchmark sobre los mismos documentos **actualiza** filas, no las duplica.
9. Cambiar de vista o de chip **no dispara ninguna llamada a IA**: todo se recalcula sobre datos ya cargados.
10. Un no-administrador-técnico recibe **403 del servidor**, no solo botones ocultos.

---

## 10. ORDEN DE IMPLEMENTACIÓN SUGERIDO

1. Módulo de comparación/normalización compartido + sus tests unitarios. **Todo lo demás depende de que este sea correcto.**
2. Endpoint de auditoría + tabla de 3 columnas + badge de acierto.
3. Badges de motor, origen y consenso.
4. Ranking por motor dentro del documento (incluida la fila de estructuras repetidas).
5. Motor de benchmark + tabla + índice único + ejecución sobre un solo documento.
6. Lote retroactivo con candado, progreso y guardas.
7. Endpoint de ranking agregado.
8. UI del laboratorio: tabla → barras → tarjetas de mejor combinación → mapa de calor → líneas.
9. Comparativa visual de preprocesado.

Después de cada paso, verifica contra el criterio de aceptación correspondiente antes de seguir.

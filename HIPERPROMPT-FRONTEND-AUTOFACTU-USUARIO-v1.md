# HIPERPROMPT — Rediseño de frontend de Autofactu · Fase 1: FLUJO DE USUARIO

> **Para pegar en Claude Code (VS Code) sobre el repositorio `Juliohes/Autoken-facturas`, rama `feat/autofactu-rollout-r051`.**
> Documento de diseño + ingeniería. Español castellano. Todo el código que generes debe ir completo, nunca resumido ni con `...`.

---

## 0. TU ROL Y TU MISIÓN

Actúas simultáneamente como:

1. **Diseñador de producto / UI senior (nivel Stripe · Linear · Holded)** — sistema de diseño, jerarquía visual, microinteracción, accesibilidad.
2. **Ingeniero frontend senior (React 18 + TypeScript + Vite + Tailwind + TanStack)** — código mantenible, tipado estricto, tests que no se rompen.
3. **Experto en seguridad (nivel INCIBE/CCN-CERT)** — señalas cualquier riesgo aunque no se pida; nunca sacrificas seguridad por velocidad.

**Misión de esta fase:** convertir el frontend del **flujo de usuario** (la persona que hace fotos y sube facturas) de un aspecto “de wireframe funcional” a un producto **profesional, pulido y preciso**, adoptando la **Dirección A “Claridad”** (claro + navegación lateral/inferior, naranja de marca reservado a la acción principal), **sin romper nada de lo que ya funciona** y **sin tocar todavía** las pantallas de administración/plataforma.

**Estándar de calidad: tolerancia cero al error.** Cada PR es tu mejor trabajo posible. Si una decisión es tuya (arquitectura de tokens, elección de librería, patrón de componente), la tomas con criterio y la justificas. Solo preguntas lo que únicamente el negocio puede saber.

---

## 1. CONTEXTO REAL DEL PROYECTO (verificado en el repo, no inventes sobre esto)

- **Producto:** Autofactu by Autoken. SaaS **multi-asesoría white-label** de digitalización de facturas con OCR/IA. Multi-tenant por subdominio (`setex.autoken.es`, `ilex.autoken.es`), aislamiento total (Postgres RLS).
- **Stack frontend real (rama r051):**
  - React `18.3`, TypeScript `5.6`, Vite `5.4`, **Tailwind CSS `3.4`** (sin librería de componentes instalada: **no hay shadcn/ui pese a lo que dice el README**).
  - `@tanstack/react-query 5`, `@tanstack/react-table 8.21`.
  - `react-router-dom 6.30` (SPA).
  - **Iconos: SVG inline a mano** (no hay librería de iconos).
  - **PWA:** `vite-plugin-pwa` + Workbox → **funciona offline / instalable**. Consecuencia de diseño: **no dependemos de recursos externos en runtime** (fuentes incluidas). Ver §4.3.
  - OpenCV (`@techstark/opencv-js`) + **motor de escáner propio en Web Worker** (`scanner.worker.ts`, `useScannerEngine`).
- **Roles:** `platform_admin`, `tenant_admin`, `user`. **Home del rol `user` = `/capturar`.**
- **Tema por tenant YA existe** (deuda parcialmente resuelta): `features/tenancy/theme.ts` inyecta en `documentElement` las variables `--color-primary` y `--color-secondary` a partir de la config del tenant (`color_primary` por defecto = naranja Autoken). **Debes construir sobre esto, no duplicarlo.**
- **Deuda conocida a corregir en esta fase:** `tailwind.config.js` **redefine las paletas `slate` y `emerald` de Tailwind** con los colores de marca (hack para cambiar toda la app sin tocar cada pantalla). Es frágil y bloquea el theming por tenant real. La sustituimos por una **capa de tokens semánticos** (§4).

### 1.1 Feature flags YA existentes (respétalos siempre; llegan en `user.feature_flags`)

| Flag | Efecto | Comportamiento por defecto |
|---|---|---|
| `scanner_v2_enabled` | Escáner en vivo (detección de bordes + autocaptura) | Activado salvo `=== false` |
| `continuous_capture_enabled` | Modo “Varias facturas” (captura continua) | Activado salvo `=== false` |
| `review_inbox_enabled` | Pantalla “Mis facturas” (`/mis-facturas`) | Activado salvo `=== false` |

**Regla de oro:** todo cambio visual debe funcionar con cada flag en ON y en OFF. No introduzcas un rediseño que asuma un flag activo.

---

## 2. ALCANCE ESTRICTO DE ESTA FASE

### ✅ DENTRO (rediseñar ahora — flujo de usuario)

| Pantalla | Ruta | Ficheros clave (reales) |
|---|---|---|
| **Capturar factura** | `/capturar` | `features/capture/CaptureScreen.tsx`, `CapturePreview.tsx`, `DocumentOverlay.tsx`, `useScannerEngine.ts`, `scannerConfig.ts`, `continuousCapture.ts` |
| **Revisar y confirmar** | `/confirmar/:fileId` | `features/confirmation/ConfirmationScreen.tsx`, `FieldRow.tsx`, `CounterpartyVerdictBlock.tsx`, `confidence.ts`, `verdict.ts`, `useReviewDraft.ts`, `useDraftAutosave.ts` |
| **Mis facturas (inbox)** | `/mis-facturas` | `features/inbox/InvoiceInbox.tsx`, `InboxItem.tsx`, `useInvoiceInbox.ts` |
| **Historial** | `/historial` | `features/history/InvoiceHistory.tsx`, `useInvoiceHistory.ts` |
| **Login** | `/login` | `features/session/LoginScreen.tsx` |
| **App shell del rol `user`** | — | `app/Menu.tsx`, `App.tsx`, layout responsive |
| **Sistema de diseño / tokens** | — | `tailwind.config.js`, `index.css`, `features/tenancy/theme.ts`, nuevos `src/ui/*` |

### ⛔ FUERA (NO tocar todavía — se hará después con el MISMO branding)

- `features/panel/*` (Panel de facturas del admin), `features/companies/*`, `features/platform/*`, `features/supervision/*` (pendientes de equipo).
- No cambies su lógica ni su markup. Si tu capa de tokens los afecta visualmente “gratis”, **verifica que no se degradan** pero no los rediseñes.

> **Prioridad absoluta del negocio (Julio):** primero dejar **fino y preciso** el flujo del usuario que hace fotos (capturar, subir archivo, varias hojas, varias facturas, ver sus facturas, estados pendientes). El panel y todo lo de admin va **después**.

---

## 3. PRINCIPIOS DE DISEÑO NO NEGOCIABLES

1. **Dirección A “Claridad”.** Fondo claro neutro azulado, superficies blancas, **navy** de marca en estructura/tipografía, **naranja** (= `--color-primary` del tenant) **solo** en la acción principal y el estado activo. Semántica (ok/warn/bad) es aparte del acento.
2. **Mobile-first de verdad.** El usuario captura desde el móvil. Diseña primero a 390px; escala a escritorio después. Áreas táctiles ≥ 44×44px. Zonas de acción al alcance del pulgar.
3. **Dual theme (claro + oscuro) desde el primer día**, ambos con el mismo sistema de tokens. El oscuro reutiliza la identidad navy actual.
4. **Accesibilidad AA obligatoria** (§6). El estado **nunca** se comunica solo por color: siempre color **+ icono + texto**.
5. **No romper producción.** Cambios visuales por tokens y componentes; **no** alteres lógica de negocio, contratos de API, ni los `data-testid` existentes. Los tests deben seguir pasando.
6. **Coherencia > creatividad puntual.** Todo sale del sistema de tokens y de la librería de componentes `src/ui`. Nada de estilos “a mano” sueltos en las pantallas.
7. **Rendimiento y PWA.** Nada que rompa el offline ni que dependa de red externa en runtime. Respeta `prefers-reduced-motion`.

---

## 4. SISTEMA DE DISEÑO (haz esto ANTES que las pantallas)

### 4.1 Eliminar el hack de Tailwind e introducir tokens semánticos

**Paso 1 — `tailwind.config.js`:** deja de redefinir `slate`/`emerald`. Mapea colores a variables CSS semánticas para poder usar clases utilitarias `bg-surface`, `text-fg`, `border-line`, `bg-accent`, etc.

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        // Todos apuntan a tokens CSS (definidos en index.css). Con <alpha-value>
        // para que las utilidades de opacidad de Tailwind sigan funcionando.
        bg:        'rgb(var(--bg) / <alpha-value>)',
        surface:   'rgb(var(--surface) / <alpha-value>)',
        'surface-2':'rgb(var(--surface-2) / <alpha-value>)',
        line:      'rgb(var(--border) / <alpha-value>)',
        fg:        'rgb(var(--fg) / <alpha-value>)',
        muted:     'rgb(var(--muted) / <alpha-value>)',
        faint:     'rgb(var(--faint) / <alpha-value>)',
        brand:     'rgb(var(--brand) / <alpha-value>)',
        accent:    'rgb(var(--accent) / <alpha-value>)',
        'accent-fg':'rgb(var(--accent-fg) / <alpha-value>)',
        ok:        'rgb(var(--ok) / <alpha-value>)',
        'ok-bg':   'rgb(var(--ok-bg) / <alpha-value>)',
        warn:      'rgb(var(--warn) / <alpha-value>)',
        'warn-bg': 'rgb(var(--warn-bg) / <alpha-value>)',
        bad:       'rgb(var(--bad) / <alpha-value>)',
        'bad-bg':  'rgb(var(--bad-bg) / <alpha-value>)',
      },
      borderRadius: { card: '16px', ctl: '10px' },
      boxShadow: {
        card: '0 1px 2px rgb(16 26 46 / .04), 0 8px 24px -12px rgb(16 26 46 / .12)',
        pop:  '0 24px 60px -18px rgb(11 19 34 / .35)',
      },
      fontFamily: {
        display: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
```

> **Estrategia de migración sin romper (importante):** las pantallas fuera de alcance usan `slate-*`/`emerald-*`. Si eliminas esas paletas de golpe, cambian de aspecto. Elige UNA de estas dos vías y decláralo en el PR:
> - **Vía recomendada:** **mantén temporalmente** el bloque `slate`/`emerald` del hack en el config **además** de los nuevos tokens semánticos, y migra pantalla a pantalla del flujo usuario a las clases nuevas (`bg-surface`, etc.). Cuando el flujo usuario esté migrado, se retira el hack en la fase admin. Cero regresión visual en lo que no tocas.
> - Vía agresiva (solo si el equipo lo aprueba): migrar todo a la vez.

**Paso 2 — `index.css`:** define los tokens en `:root` (claro), en `[data-theme="dark"]` y en `@media (prefers-color-scheme: dark)` sin override explícito. El **acento consume el color del tenant** (`--color-primary` que ya inyecta `theme.ts`), con fallback al naranja de marca.

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* Marca (fijos) */
    --brand: 22 35 59;          /* #16233B navy del logotipo */
    /* Acento = color del tenant (theme.ts inyecta --color-primary como HEX).
       Fallback a naranja de marca. Ver nota de integración abajo. */
    --accent: 242 101 34;       /* #F26522 */
    --accent-fg: 255 255 255;

    /* Neutros CLAROS (Dirección A) */
    --bg: 245 247 251;          /* #F5F7FB */
    --surface: 255 255 255;
    --surface-2: 240 243 249;
    --border: 226 231 240;      /* #E2E7F0 */
    --fg: 16 26 46;             /* #101A2E */
    --muted: 92 106 133;        /* #5C6A85 */
    --faint: 136 150 172;

    /* Semántica */
    --ok: 15 157 106;  --ok-bg: 229 246 238;
    --warn: 176 115 0; --warn-bg: 251 241 220;
    --bad: 199 55 46;  --bad-bg: 251 230 228;

    color-scheme: light;
  }

  [data-theme="dark"] {
    --brand: 232 237 245;
    --accent: 255 122 61;       /* #FF7A3D naranja algo más luminoso en oscuro */
    --accent-fg: 20 26 40;
    --bg: 11 19 34;             /* #0B1322 */
    --surface: 16 26 46;        /* #101A2E */
    --surface-2: 22 49 77;      /* #16314D aprox */
    --border: 34 49 77;         /* #22314D */
    --fg: 232 237 245;
    --muted: 142 160 189;
    --faint: 95 113 154;
    --ok: 61 220 151;  --ok-bg: 15 42 34;
    --warn: 255 200 107; --warn-bg: 46 36 18;
    --bad: 255 122 114;  --bad-bg: 46 22 21;
    color-scheme: dark;
  }

  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      /* misma paleta que [data-theme="dark"] — factorízala o duplícala */
    }
  }

  html, body, #root { min-height: 100%; }
  body { background: rgb(var(--bg)); color: rgb(var(--fg)); font-family: theme('fontFamily.sans'); }
  button { white-space: nowrap; }        /* regla existente, se mantiene */
}
```

> **Integración con `theme.ts` (per-tenant + dual-theme) — decide y documenta:** `theme.ts` hoy hace `setProperty('--color-primary', hex)`. Como los tokens usan formato `R G B` (para `<alpha-value>`), tienes dos opciones limpias: (a) que `theme.ts` inyecte el acento del tenant como triplete RGB en `--accent` (convierte el hex a `"r g b"` al aplicarlo); o (b) mantener `--color-primary` en hex y definir `--accent` a partir de él sin alpha. **Recomendación:** opción (a), una función `hexToRgbTriplet()` en `theme.ts`, para que el acento del tenant funcione con opacidades. Mantén `--color-primary`/`--color-secondary` para no romper lo que ya los consume.

### 4.2 Toggle de tema

Añade un control de tema (claro / oscuro / sistema) que escriba `data-theme` en `documentElement` y persista en `localStorage`. Respeta “sistema” por defecto. Colócalo en el shell (menú de usuario). **No** uses `localStorage` como única fuente de verdad sin try/catch (modo incógnito).

### 4.3 Tipografía (crítico por ser PWA)

- Parejas: **Plus Jakarta Sans** (display/títulos) + **Inter** (texto/UI). Cifras con `font-variant-numeric: tabular-nums`.
- **No enlaces Google Fonts por CDN** (romperías el offline y añades dependencia externa / posible bloqueo por CSP). **Auto-hospeda** con `@fontsource/plus-jakarta-sans` y `@fontsource/inter` (o `@fontsource-variable/*`), importados en el bundle, con `font-display: swap`. Declara SIEMPRE stack de fallback del sistema.
- Escala de tipo (rem, base 16px): 12 / 13 / 14 / 16 / 18 / 20 / 24 / 30. Títulos con `text-wrap: balance`. Cuerpo ≤ ~65 car.

### 4.4 Iconos

- Instala **`lucide-react`** (aprobado). Reemplaza los SVG a mano **de las pantallas dentro de alcance**, con tamaño coherente (16/18/20px) y `aria-hidden` cuando sean decorativos. No toques los SVG de pantallas fuera de alcance en esta fase.

### 4.5 Librería de componentes `src/ui/` (crea estos primitivos y úsalos en todas las pantallas)

Componentes headless propios (ligeros, tipados, accesibles). **No** hace falta traer shadcn entero; si usas Radix para primitivos con foco/teclado (Dialog, Dropdown), justifícalo. Contrato mínimo:

- `Button` — variantes: `primary` (acento), `secondary`, `ghost`, `danger`; tamaños `sm|md|lg`; estados `loading`, `disabled`; `iconLeft/iconRight`. Foco visible.
- `Card` / `Section` (título en versalitas, cuerpo).
- `Field` (label + input/select + hint + error accesible con `aria-describedby`).
- `StatusBadge` — mapea estado → { color, icono lucide, texto }. Única fuente de verdad de estados (§5.3/§5.4).
- `SegmentedControl` (para Recibida/Emitida y selector de modo).
- `Sheet`/`Modal` accesible (foco atrapado, cierre con Esc, `aria-modal`).
- `Spinner`, `EmptyState`, `Toast`/`Banner` (info/ok/warn/bad).
- `AppShell` responsive (§5.1).

Cada componente: un fichero `.tsx` + su test mínimo. Documenta props con JSDoc en español.

---

## 5. ESPECIFICACIÓN PANTALLA POR PANTALLA (flujo usuario)

> Para cada pantalla respeta la lógica y los `data-testid` existentes. Rediseña **estructura visual, jerarquía, estados y microcopy**, no el comportamiento.

### 5.1 App shell del rol `user` (mobile-first)

- **Móvil:** cabecera fina con **logo del tenant** (usa `theme.logoUrl`, `referrerPolicy="no-referrer"`) + menú de usuario (avatar → tema, cerrar sesión). **Navegación inferior fija (bottom-tab)** con 2 destinos del usuario: **Subir** (`/capturar`, icono `camera`) y **Mis facturas** (`/mis-facturas`, icono `receipt`/`files`), respetando `review_inbox_enabled`. La barra inferior no debe tapar acciones; respeta `env(safe-area-inset-bottom)`.
- **Escritorio:** sidebar izquierda (patrón Dirección A) con los mismos destinos.
- El menú actual (`app/Menu.tsx`) deriva enlaces de `routes.ts` por rol — **mantén esa fuente única**, solo cambia la presentación (bottom-tab en móvil / sidebar en desktop).

### 5.2 Capturar factura — `/capturar` (LA PANTALLA ESTRELLA, máxima dedicación)

Estados y modos reales a cubrir (respeta flags):

**A) Estado inicial (`camera.status === 'idle'`)**
- Selector **Recibida / Emitida** como `SegmentedControl` grande.
- Si `tenant_admin`: selector de **Empresa** (el `user` no lo ve; su empresa es fija).
- **Botón obturador primario gigante** (“Tomar foto”, circular, acento) centrado y al alcance del pulgar.
- Acciones secundarias: **Subir archivo**, **Varias hojas** (multipágina) y, si `continuous_capture_enabled`, **Varias facturas** (captura continua). Jerarquía clara: el obturador manda; el resto son secundarios (`ghost`).
- Enlace discreto “Ver historial”.

**B) Cámara activa (`camera.status === 'active'`) con escáner en vivo (`scanner_v2_enabled`)**
- Visor a pantalla completa. Superpón `DocumentOverlay` que ya expone estados **`none | detected | good | stabilizing | auto_armed`**. Diséñalos con **color + copy** (no solo color):
  | Estado overlay | Marco | Copy guía |
  |---|---|---|
  | `none` | tenue/gris | “Coloca la factura dentro del marco” |
  | `detected` | acento suave | “Documento detectado” |
  | `good` | ok/verde | “Perfecto, mantén firme” |
  | `stabilizing` | ok pulsante | “Estabilizando…” |
  | `auto_armed` | ok fuerte + progreso | “Capturando…” (autocaptura) |
- Controles inferiores en gradiente legible: **Capturar**, **Linterna** (solo si `torchAvailable`), **Subir archivo**, **Cerrar cámara**. Deshabilita “Capturar” hasta `videoReady` con copy “Preparando cámara…”.
- Guía de encuadre (recuadro + esquinas). Mensaje de página en multipágina (“Página 1: datos fiscales”, etc.).

**C) Previsualización (`CapturePreview`: `idle | uploading | saved`)**
- Miniatura de lo capturado + acciones **Repetir** / **Usar foto**. En `uploading`: “Guardando factura…” con spinner; en `saved`: “✓ Guardada” en verde. Botones deshabilitados mientras `busy`.

**D) Multipágina (“Varias hojas”)**
- Tira de miniaturas ordenadas con “Quitar página N”, aviso de mínimo 2 / máximo 5, y **Enviar factura**.

**E) Captura continua (“Varias facturas”, `continuous_capture_enabled`)**
- Contador “N de M facturas aceptadas”, lista de aceptadas, avisos (`continuousNotice`) con `role="status"`. Mantiene el stream vivo entre disparos.

**F) Procesando / errores**
- Estado “Procesando factura…” a pantalla centrada con spinner.
- Errores no bloqueantes (subida fallida, cámara insegura/no disponible, límite de páginas) como `Banner`/texto `role="alert"`, con acción de reintento y **siempre** la alternativa “Subir archivo”.

**Requisitos de diseño de esta pantalla:** táctil, sin texto que se parta, contraste alto sobre el visor oscuro, animaciones sujetas a `prefers-reduced-motion`, y que **todo funcione con `scanner_v2_enabled=false`** (sin overlay en vivo, captura manual).

### 5.3 Revisar y confirmar — `/confirmar/:fileId`

- Estados de carga: “Leyendo la factura…” (OCR en curso) vs “Cargando datos de revisión…”. Error: “No se pudo abrir esta factura” + “Repetir foto”.
- **Marcas de confianza por campo** (de `confidence.ts`): `ok | dudoso | revisar | no_leido`. Renderízalas con `StatusBadge` = **color + icono + texto** (AA):
  | Marca | Color | Icono lucide | Texto |
  |---|---|---|---|
  | `ok` | ok/verde | `check-circle` | “Fiable” |
  | `dudoso` | warn/ámbar | `alert-circle` | “Dudoso” |
  | `revisar` | warn/ámbar | `alert-triangle` | “Dudoso, revisar” |
  | `no_leido` | bad/rojo | `x-circle` | “No leído” |
- **Verificación de CIF de contraparte** (de `verdict.ts`: tono `ok|warn|error`) con `CounterpartyVerdictBlock`: mensajes reales (“CIF verificado”, “no es válido”, “No encontramos ese CIF”, “No se pudo verificar”). Marca visible “✓ CIF verificado”.
- **Secciones** (4 siempre visibles, decisión ya tomada en el repo): **Contraparte · Documento · Importes**, y **Tramos de IVA/IRPF** con su desplegable interno (tasas cerradas {21,10,4, Sin IVA}). Rediséñalas como `Section`/`Card` con `FieldRow` consistentes.
- **Aviso de baja nitidez** (no bloqueante, una sola vez): `Banner warn` “Esta foto puede estar borrosa. Revisa bien los datos antes de confirmar.”
- **Autoguardado de borrador** (`useDraftAutosave`): muestra un indicador sutil “Guardado” / “Guardando…” sin robar protagonismo.
- **Acciones**: `Confirmar y guardar` (primary) + `Repetir foto` (ghost). Zona de acción fija y accesible en móvil.
- Si hay imagen, mini-previsualización del documento (patrón de dos columnas en escritorio; apilado en móvil).

### 5.4 Mis facturas (inbox) — `/mis-facturas` (`review_inbox_enabled`)

- Título “Mis facturas” + subtítulo “Solo aparecen las facturas que has subido tú.”
- **Resumen** en 3 tarjetas: **Procesando · Listas · Revisar** (de `summary`).
- **Lista `InboxItem`** con estado real → `StatusBadge` + acción contextual:
  | `status` | Texto estado | Acción |
  |---|---|---|
  | `pending_ocr` | “En cola” | “Ver progreso” |
  | `processing` | “Procesando” | “Ver progreso” |
  | `ocr_done` | “Lista para revisar” | “Revisar factura” |
  | `needs_review` | “Pendiente de comprobación” | “Revisar factura” |
  | `capture_unreadable` | “No se pudo leer” | “Repetir foto” → `/capturar` |
  | `ocr_failed` | “Error de lectura” | “Reintentar lectura” |
- Cada item muestra `page_count` (“N páginas”) y fecha. Toda la fila es un objetivo táctil cómodo.
- **Empty state** con ilustración/icono: “Todavía no has enviado ninguna factura” + CTA “Subir tu primera factura”.
- **Paginación por cursor** existente (“Cargar más”, `next_cursor`): mantenla; mejora el estado de carga.
- Si `review_inbox_enabled === false`: mantiene el fallback actual (no rediseñes lógica, solo estilo).

### 5.5 Historial — `/historial`

- Lista de envíos con estado y acción contextual (misma semántica de estados que inbox). Aplica el sistema de tokens y `StatusBadge`. Empty state coherente.

### 5.6 Login — `/login`

- Aplica tokens (Dirección A en claro / navy en oscuro). Tarjeta centrada, logo del tenant, campos accesibles, badge “Verificación en dos pasos” cuando `totpRequired`, botón `Entrar` full-width con estado `loading`. Copy de confianza discreto (“Acceso cifrado · aislamiento por asesoría”).

---

## 6. ACCESIBILIDAD (AA) — CHECKLIST OBLIGATORIO

- Contraste texto/fondo ≥ **4.5:1** (texto normal) y **3:1** (texto grande/UI). Verifica el naranja sobre blanco: úsalo para **fondos de acción con texto blanco**, no como texto naranja sobre blanco en tamaños pequeños.
- **Nunca solo color:** estado = color + icono + texto (ya previsto en `StatusBadge`).
- Foco de teclado **siempre visible** (`:focus-visible`), orden lógico, `Sheet/Modal` con foco atrapado y cierre con Esc.
- Objetivos táctiles ≥ 44×44px. Inputs con `label` asociado; errores con `role="alert"` + `aria-describedby`.
- Imágenes decorativas `aria-hidden`; significativas con `alt`. Vídeo de cámara con etiqueta.
- `prefers-reduced-motion`: desactiva animaciones no esenciales (pulsos del overlay, transiciones largas).
- Textos en **español**, claros y orientados a la acción (“Capturar”, luego “Guardada”). Errores explican qué pasó y cómo seguir.

---

## 7. INGENIERÍA Y GUARDARRAÍLES (no romper nada)

1. **No cambies** contratos de API, tipos generados (`api/schema.d.ts`), ni la lógica de hooks (`use*`). Rediseñas **presentación**.
2. **Conserva todos los `data-testid`** y roles ARIA usados por los tests. Si un test comprueba texto que cambias por microcopy, **actualiza el test** y justifícalo en el PR (no borres cobertura).
3. **Tests verdes**: `npm run test`, `lint` y `typecheck` deben pasar en cada PR. Añade tests de los nuevos componentes `src/ui`.
4. **Feature flags**: cada pantalla debe verse bien con sus flags en ON y OFF.
5. **PWA/offline intacto**: fuentes e iconos en el bundle (nada de CDN en runtime). No añadas peticiones de red en el arranque.
6. **Rendimiento**: no re-renders innecesarios; memoiza listas; imágenes de cámara liberadas (`revokeObjectURL`) como ya se hace. No metas librerías pesadas sin justificar tamaño.
7. **Seguridad (proactivo)**: mantén `referrerPolicy="no-referrer"` en el logo del tenant; no introduzcas `dangerouslySetInnerHTML`; valida que el toggle de tema y `localStorage` van en try/catch. Señala cualquier riesgo que detectes.
8. **Sin regresión en lo fuera de alcance**: tras migrar tokens, abre las pantallas de admin y confirma que no se rompen (por eso se recomienda mantener el hack `slate/emerald` temporalmente).

---

## 8. PLAN DE EJECUCIÓN POR PRs (incremental, revisable)

Trabaja en **ramas `feature/<slug>` partiendo de `feat/autofactu-rollout-r051`**. Un PR por bloque, pequeño y revisable. Cuando el flujo usuario esté fino, se integrará a `develop` y luego a `main` (lo hará Julio).

1. **PR 1 — Fundamentos del sistema de diseño:** tokens en `index.css`, `tailwind.config.js` (con hack legacy conservado), auto-hosting de fuentes, `lucide-react`, toggle de tema. Sin cambios de pantalla todavía. Screenshots claro/oscuro.
2. **PR 2 — Librería `src/ui`:** `Button`, `Card`, `Field`, `StatusBadge`, `SegmentedControl`, `Sheet`, `Spinner`, `EmptyState`, `Banner`, `AppShell`. Con tests.
3. **PR 3 — App shell del usuario** (bottom-tab móvil / sidebar desktop) + Login.
4. **PR 4 — Capturar** (idle, cámara+overlay, preview, multipágina, continua, errores). Es el PR más grande; si conviene, divídelo (4a idle+preview, 4b overlay+modos).
5. **PR 5 — Confirmar** (marcas de confianza, verdict CIF, secciones, autosave, aviso nitidez).
6. **PR 6 — Mis facturas + Historial** (resumen, estados, empty, cargar más).
7. **PR 7 — Pulido y a11y**: auditoría AA, `prefers-reduced-motion`, revisión responsive 360/390/768/1024/1440, capturas antes/después.

Cada PR incluye: descripción, decisiones de diseño tomadas, **capturas claro+oscuro móvil+escritorio**, y checklist de a11y.

---

## 9. LO QUE NO DEBES HACER

- ❌ Rediseñar panel/admin/plataforma/supervisión en esta fase.
- ❌ Cambiar lógica de negocio, endpoints, tipos generados o el motor de escáner.
- ❌ Introducir dependencias de red en runtime (romper PWA) o fuentes por CDN.
- ❌ Comunicar estado solo por color.
- ❌ Borrar tests o `data-testid` para “que pase”.
- ❌ Asumir un feature flag activo.
- ❌ Meter una librería de UI pesada “porque sí”. Justifica cada dependencia por tamaño y valor.

---

## 10. CÓMO EMPEZAR (primer turno del agente)

1. Confirma que estás en `feat/autofactu-rollout-r051`. Lee `tailwind.config.js`, `index.css`, `features/tenancy/theme.ts`, `App.tsx`, `app/Menu.tsx`, `app/routes.ts` y las pantallas en alcance **completas** antes de escribir nada.
2. Presenta un **plan breve** (qué PRs, qué componentes, qué decisiones de tokens) y **espera OK** antes de ejecutar PR 1.
3. Al terminar cada tarea significativa, incluye el bloque **🔍 PREGUNTAS DEL EXPERTO** (10–20, ordenadas por impacto) y responde tú mismo las que sean decisión técnica; deja para Julio solo las de negocio.

---

## 11. DECISIONES YA CERRADAS POR JULIO (no vuelvas a preguntarlas)

- Dirección visual: **A “Claridad”** (con captura móvil inspirada en la Dirección C).
- **Modo claro y oscuro**: ambos.
- **Iconos**: `lucide-react`.
- **Sistema de tokens semánticos**: sí, sustituyendo el hack de Tailwind (con la estrategia de no-regresión del §4.1).
- **Compatibilidad**: se mantiene Tailwind; shadcn no es obligatorio (primitivos propios en `src/ui`, Radix solo si aporta a11y real).
- **Prioridad**: primero el **flujo de usuario** (captura/subida/mis facturas/estados). Admin, después, con el mismo branding.
- **Rama base**: `feat/autofactu-rollout-r051`; luego se pasa a `develop`/`main`.
- **Datos masivos (panel admin, fase posterior)**: paginación en backend + virtualización en frontend (`@tanstack/react-virtual`) + búsqueda/filtros/ordenación. (No aplica al flujo usuario ahora, anotado para la fase admin.)
- **A11y**: AA obligatorio. **Seguridad**: señalar riesgos siempre; CSP y validación de `Content-Type` del logo se abordarán en backend.

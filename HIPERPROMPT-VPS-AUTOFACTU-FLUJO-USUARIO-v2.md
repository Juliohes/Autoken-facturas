# HIPERPROMPT (VPS) — Rediseño de frontend de Autofactu · Flujo de USUARIO · v2

> **Para ejecutar en el VPS con Claude Code / tu IA de terminal, sobre `github.com/Juliohes/Autoken-facturas`, rama `feat/autofactu-rollout-r051` (HEAD actual `0992fa2`).**
> El objetivo es dejar el **flujo de usuario** impecable y profesional y, cuando esté **fino y verificado**, **subirlo a GitHub**. Español castellano. Todo el código que generes debe ir **completo**, nunca resumido ni con `...`.

---

## 0. TU ROL, TU MISIÓN Y TU ESTÁNDAR

Actúas a la vez como **diseñador de producto/UI senior**, **ingeniero frontend senior (React 18 + TS + Vite + Tailwind + TanStack)** y **experto en seguridad**. Tolerancia cero al error: cada bloque es tu mejor trabajo. Tomas tú las decisiones técnicas con criterio; solo paras a preguntar lo que únicamente el negocio puede saber.

**Misión:** llevar el **flujo de usuario** (la persona que hace fotos y sube facturas) a un frontend **completo y profesional** en la **Dirección A “Claridad”** (claro, plano, legible; navy de marca en la estructura y naranja solo en la acción principal), **sobre el sistema de diseño que ya existe** (`--tn-*`), **sin romper nada** y **sin tocar todavía** admin/plataforma. Al terminar y verificar, **subes a GitHub**.

---

## 1. CONTEXTO REAL (verificado en el repo el 01/09/2026 — no inventes sobre esto)

- **Producto:** Autofactu by Autoken. SaaS multi-asesoría white-label, multi-tenant por subdominio (`setex.autoken.es`, `ilex.autoken.es`), Postgres RLS. PWA offline (`vite-plugin-pwa` + Workbox).
- **Stack:** React 18.3, TS 5.6, Vite 5.4, **Tailwind 3.4**, `@tanstack/react-query 5`, `@tanstack/react-table 8.21`, `react-router-dom 6.30`. OpenCV + **escáner propio en Web Worker**. **No hay** shadcn ni librería de iconos (SVG a mano).
- **Ya existe un sistema de diseño** en `frontend/src/index.css` (~936 líneas): tokens `--tn-*` (colores, radios, sombras, glass), clases de componente (`.tn-app-shell`, `.tn-user-nav`, `.tn-login-card`, `.tn-capture-*`, `.tn-inbox-item`, `.tn-summary-card`, `.tn-liquid-glass`, `.tn-primary-action`, `.tn-secondary-action`, etc.). **Extiéndelo, NO lo tires.**
- **Paleta de marca (fija):** navy `#021231` (`--color-secondary`/`--brand-navy`), naranja `#FA6703` (`--color-primary`/`--brand-orange`), fondo `#F4F7FB`. El acento por tenant entra por `--color-primary` (theme.ts).
- **Solo tema claro** hoy: `color-scheme: light`, sin bloques de modo oscuro. Hay que **añadir modo oscuro** (claro/oscuro/sistema).
- **Navegación de usuario (R-056), 4 destinos** en `frontend/src/app/Menu.tsx` + `routes.ts`:
  - **Escáner** → `/capturar` (home del rol `user`)
  - **Subir Archivo** → `/subir-archivo`
  - **Pendientes** → `/mis-facturas` (reetiquetado; reutiliza el inbox)
  - **Historial** → `/historial` (solo confirmadas, 4 meses, solo lectura)
- **Feature flags** en `user.feature_flags` (todo debe funcionar en ON y OFF): `scanner_v2_enabled`, `continuous_capture_enabled` (modo “Varias facturas” **oculto** en UI, lógica conservada), `review_inbox_enabled`.
- **Base de tests:** `frontend` con ~**55 ficheros de test** y suite en verde. Hay un **test de regresión del overlay** (`fill="none"`, sin relleno sólido): no lo rompas.

### 1.1 Deuda/inconsistencias reales a corregir (verificadas)
- `features/inbox/InvoiceInbox.tsx` tiene `<h1>Mis facturas</h1>` aunque el menú dice **“Pendientes”** → unifícalo a “Pendientes”.
- Quedan **clases del tema oscuro heredado** sueltas en el flujo usuario (`text-emerald-400`, `text-slate-100`, `border-slate-600`, `text-red-400`, etc., p. ej. en `InboxItem.tsx`, `InvoiceHistory.tsx`) que ahora dependen del hack de `tailwind.config.js` (paletas `slate`/`emerald` reasignadas). Sustitúyelas por tokens/`--tn-*` en las pantallas **dentro de alcance**.
- El **glass** (`--glass-navy-*`, `.tn-liquid-glass`) es vistoso pero arriesga el contraste AA del texto encima. En Dirección A se reduce a acentos puntuales; ver §3 y §4.

---

## 2. ALCANCE

### ✅ DENTRO (rediseñar ahora — flujo de usuario)
| Pantalla | Ruta | Ficheros reales |
|---|---|---|
| **Escáner** | `/capturar` | `features/capture/CaptureScreen.tsx`, `CapturePreview.tsx`, `DocumentOverlay.tsx`, `useScannerEngine.ts`, `scannerConfig.ts` |
| **Subir Archivo** | `/subir-archivo` | `features/upload/UploadFileScreen.tsx` |
| **Revisar y confirmar** | `/confirmar/:fileId` | `features/confirmation/ConfirmationScreen.tsx`, `FieldRow.tsx`, `CounterpartyVerdictBlock.tsx`, `confidence.ts`, `verdict.ts`, `useDraftAutosave.ts` |
| **Pendientes** | `/mis-facturas` | `features/inbox/InvoiceInbox.tsx`, `InboxItem.tsx`, `useInvoiceInbox.ts` |
| **Historial** | `/historial` | `features/history/InvoiceHistory.tsx`, `useInvoiceHistory.ts` |
| **Login** | `/login` | `features/session/LoginScreen.tsx` |
| **Shell + navegación usuario** | — | `app/Menu.tsx`, `app/AppRoutes.tsx`, `App.tsx` |
| **Sistema de diseño** | — | `index.css`, `tailwind.config.js`, `features/tenancy/theme.ts`, nuevo `src/ui/*` |
| **Processing** (pantalla intermedia) | — | `features/processing/*` (aplícale tokens; sin rediseño mayor) |

### ⛔ FUERA (NO tocar todavía — se hará después con el mismo branding)
`features/panel/*`, `features/companies/*`, `features/platform/*`, `features/supervision/*`. No cambies su lógica ni su markup. Tras migrar tokens, **verifica que no se degradan** (no los rediseñes).

> **Prioridad del negocio (Julio):** primero el flujo del usuario que hace fotos (Escáner, Subir Archivo, Varias hojas, Pendientes, Historial). Admin/panel va **después**, con el mismo branding.

---

## 3. DIRECCIÓN DE DISEÑO Y REGLAS NO NEGOCIABLES

1. **Dirección A “Claridad”**: claro, superficies blancas, jerarquía tipográfica marcada, navy en estructura, **naranja solo en la acción principal y el estado activo**. El glass se degrada a detalle puntual (no como base de todo).
2. **Mobile-first real**: el usuario captura desde el móvil. Diseña a 390px primero. Objetivos táctiles ≥ 44×44px. Acciones al alcance del pulgar.
3. **Modo claro + oscuro** con el mismo sistema de tokens (`--tn-*`), conmutable (claro/oscuro/sistema).
4. **Accesibilidad AA obligatoria.** El estado nunca se comunica solo por color: **color + icono + texto**.
5. **A11y del naranja (verificado con WCAG):** naranja `#FA6703` + texto **blanco** = **3.0:1** (❌ falla texto normal). + texto **navy `#021231`** = **6.18:1** (✅). Naranja como **texto** sobre fondo claro = **2.79:1** (❌). → **Los botones/acentos naranja llevan texto NAVY, no blanco.** Si en algún sitio se exige texto blanco sobre naranja, usa una variante oscura `--tn-accent-strong` (~`#C24E00`, que sí pasa 4.5:1 con blanco) y reserva `#FA6703` para superficies grandes/iconos. Nunca uses `#FA6703` como color de texto sobre claro.
6. **No romper producción**: cambios por tokens y componentes; no toques lógica de negocio, contratos de API, tipos generados (`api/schema.d.ts`) ni los `data-testid`. Los tests deben seguir verdes.
7. **Coherencia > creatividad puntual**: todo sale del sistema de tokens y de `src/ui`. Nada de estilos ni HEX sueltos en las pantallas.
8. **PWA intacta**: nada que rompa el offline ni que dependa de red externa en runtime. Respeta `prefers-reduced-motion`.

---

## 4. SISTEMA DE DISEÑO (haz esto ANTES que las pantallas)

### 4.1 Consolidar tokens y añadir modo oscuro (extiende `index.css`, no lo reescribas)
- Mantén los `--tn-*` existentes. Añade explícitamente el **token de texto sobre acento** y la **variante fuerte**:

```css
:root{
  /* ...los --tn-* actuales se conservan... */
  --tn-accent: var(--brand-orange);          /* #FA6703 */
  --tn-accent-ink: var(--brand-navy);        /* texto NAVY sobre naranja (AA 6.2:1) */
  --tn-accent-strong: #c24e00;               /* naranja oscuro: úsalo si hace falta texto blanco */
}
```

- Aplica `--tn-accent-ink` a **todos** los elementos naranja con texto (`.tn-primary-action`, botones primarios, chips de estado activo, nav activo). Sustituye cualquier `color:#fff`/`text-white` sobre naranja por navy.
- **Modo oscuro**: define el tema por `data-theme="dark"` en `documentElement`, redefiniendo SOLO los tokens (no los componentes). Base oscura = navy `#021231` como fondo; sube la luminosidad del naranja para acentos.

```css
:root[data-theme="dark"]{
  color-scheme: dark;
  --app-background:#021231; --background-primary:#021231; --background-secondary:#06152c;
  --surface:#0a1c39; --surface-primary:#0a1c39; --surface-secondary:#0e2242; --surface-soft:#0e2242;
  --text-primary:#eaf1fb; --text-secondary:#93a6c4; --text-tertiary:#5f75a0;
  --border-default:#1c3357; --divider-default:#152a49;
  --brand-orange:#ff7a3d;               /* acento algo más luminoso en oscuro */
  --tn-accent-ink:#021231;              /* texto navy sobre naranja sigue funcionando */
  --success:#3ddc97; --success-surface:#0f2a22;
  --error:#ff7a72; --error-surface:#2e1615;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){ /* repetir el bloque oscuro de arriba */ }
}
```

- **Regla:** ningún componente define un color solo dentro de `[data-theme]`/media query; siempre a través de un token, para que ambos temas resuelvan como conjunto. Revisa antes de subir que no haya color definido únicamente en un bloque de tema.

### 4.2 Toggle de tema
Control claro/oscuro/sistema en el menú de usuario, escribe `data-theme` en `documentElement` y persiste en `localStorage` **envuelto en try/catch** (modo incógnito). Por defecto “sistema”.

### 4.3 Tipografía (crítico por PWA)
- **Plus Jakarta Sans** (títulos) + **Inter** (texto/UI). Cifras `font-variant-numeric: tabular-nums`.
- **Auto-hospeda** con `@fontsource/plus-jakarta-sans` y `@fontsource/inter` (o `@fontsource-variable/*`) importadas en el bundle, `font-display: swap`. **Nada de Google Fonts por CDN** (rompería el offline). Declara stack de fallback del sistema.

### 4.4 Iconos
Instala **`lucide-react`** y sustituye los SVG a mano **de las pantallas en alcance** (16/18/20px, `aria-hidden` si son decorativos). No toques los SVG del admin en esta fase.

### 4.5 Librería `src/ui/` (crea y reutiliza en todas las pantallas)
Primitivos propios, tipados y accesibles (Radix solo si aporta foco/teclado real):
`Button` (primary/secondary/ghost/danger, sm/md/lg, loading, iconLeft/iconRight; primario = naranja con texto navy), `Card`/`Section`, `Field` (label+control+hint+error con `aria-describedby`), **`StatusBadge`** (única fuente de verdad estado→{color,icono,texto}), `SegmentedControl` (Recibida/Emitida), `Sheet`/`Modal` accesible (foco atrapado, Esc), `Spinner`, `EmptyState`, `Banner`/`Toast`, `ThemeToggle`. Cada componente con su test mínimo.

### 4.6 Limpieza de deuda (dentro de alcance)
- Reemplaza clases heredadas `slate-*`/`emerald-*`/`red-*` por tokens/`--tn-*` en las pantallas del flujo usuario.
- Unifica `<h1>Mis facturas</h1>` → **“Pendientes”** en `InvoiceInbox.tsx`.
- Mantén el hack `slate/emerald` de `tailwind.config.js` **solo** mientras el admin no esté migrado (fase posterior); no lo retires ahora.

---

## 5. ESPECIFICACIÓN PANTALLA POR PANTALLA (respeta lógica y `data-testid`)

### 5.1 Shell + navegación usuario (mobile-first)
- **Móvil:** cabecera fina con logo del tenant (`theme.logoUrl`, `referrerPolicy="no-referrer"`) + menú (tema, cerrar sesión). Navegación de los **4 destinos** cómoda en móvil (barra inferior tipo tab o menú accesible), respetando `env(safe-area-inset-bottom)`.
- **Escritorio:** sidebar/topbar con los 4 destinos. Mantén la **fuente única** de rutas (`routes.ts`/`Menu.tsx`); solo cambia presentación.
- Estado activo con navy/naranja (texto navy sobre naranja).

### 5.2 Escáner — `/capturar` (pantalla estrella)
- **Recibida/Emitida obligatoria** (`SegmentedControl`): la captura arranca deshabilitada hasta elegir; copy guía visible.
- Botón **obturador** grande y centrado. Secundarias: **Subir archivo** y **Varias hojas** (multipágina). **No** muestres “Varias facturas” (oculto; lógica interna intacta tras su flag).
- Con `scanner_v2_enabled`: visor a pantalla completa con `DocumentOverlay` (estados **`none|detected|good|stabilizing|auto_armed`**) diseñados con **color + copy** (no solo color): none=“Coloca la factura dentro del marco”, detected=“Documento detectado”, good=“Perfecto, mantén firme”, stabilizing=“Estabilizando…”, auto_armed=“Capturando…”. **Overlay sin relleno sólido** (respeta el test `fill="none"`).
- Controles inferiores legibles: Capturar (deshabilitado hasta `videoReady`, copy “Preparando cámara…”), Linterna (si `torchAvailable`, 44×44, `aria-pressed`), Subir archivo, Cerrar cámara.
- **CapturePreview** (`idle|uploading|saved`): miniatura + Repetir/Usar foto; “Guardando factura…” / “✓ Guardada”; botones deshabilitados mientras `busy`.
- Errores no bloqueantes (subida fallida, cámara insegura/no disponible) con `role="alert"` y alternativa “Subir archivo”. Todo debe funcionar con `scanner_v2_enabled=false` (captura manual, sin overlay en vivo).

### 5.3 Subir Archivo — `/subir-archivo`
- Fieldset **Dirección** (Recibida/Emitida). Copy: “Cada imagen o PDF se envía como una factura independiente (hasta 10 por tanda).”
- **Dropzone** grande “Elegir imágenes o PDF” (`accept="application/pdf,image/*"`, múltiple). Estado por documento: subiendo / subida / falló, con `StatusBadge`. Resumen “X de N subidas · M no se pudo”. Fallos parciales tolerados. CTA “Ir a Pendientes”.

### 5.4 Revisar y confirmar — `/confirmar/:fileId`
- Marcas de confianza (`confidence.ts`: `ok|dudoso|revisar|no_leido`) con `StatusBadge` **color+icono+texto**: ok=✓ “Fiable” (verde), dudoso=● “Dudoso” (ámbar), revisar=▲ “Dudoso, revisar” (ámbar), no_leido=✕ “No leído” (rojo).
- Verificación de CIF (`verdict.ts`, tono `ok|warn|error`) con `CounterpartyVerdictBlock` y sus mensajes reales; marca “✓ CIF verificado”.
- Secciones **Contraparte · Documento · Importes** + Tramos IVA/IRPF (tasas cerradas {21,10,4,Sin IVA}). `Section`/`FieldRow` consistentes.
- Aviso de baja nitidez (no bloqueante, una vez). Indicador sutil de **autoguardado** (`useDraftAutosave`): “Guardado”/“Guardando…”. Acciones fijas y accesibles: Confirmar y guardar (primary) / Repetir foto (ghost). Mini-preview del documento (2 columnas en escritorio, apilado en móvil).

### 5.5 Pendientes — `/mis-facturas` (`review_inbox_enabled`)
- Título **“Pendientes”** (corrige el H1). Subtítulo “Solo aparecen las facturas que has subido tú.”
- Resumen 3 tarjetas: **Procesando · Listas · Revisar**. Lista `InboxItem` con estado→`StatusBadge` y acción contextual: `pending_ocr`“En cola”→Ver progreso; `processing`“Procesando OCR”→Ver progreso; `ocr_done`“Lista para revisar”→Revisar factura; `needs_review`“Pendiente de comprobación”→Revisar factura; `capture_unreadable`“No se pudo leer”→Repetir foto; `ocr_failed`“Error de lectura”→Reintentar lectura. `page_count` (“N páginas”) y fecha. Fila = objetivo táctil. Empty state con CTA “Subir tu primera factura”. Paginación por cursor (“Cargar más”). Fallback si `review_inbox_enabled===false` (solo estilo).

### 5.6 Historial — `/historial`
- Solo confirmadas, últimos 4 meses, **solo lectura**, cursor. Aplica tokens y estilo de lista coherente con Pendientes. Empty state: “Todavía no tienes facturas confirmadas en los últimos cuatro meses.”

### 5.7 Login — `/login`
- Tarjeta centrada con tokens (glass sutil admitido aquí), logo del tenant, campos accesibles, badge “Verificación en dos pasos” cuando `totpRequired`, botón Entrar full-width (loading), copy de confianza discreto.

---

## 6. ACCESIBILIDAD AA (checklist obligatorio antes de subir)
- Contraste ≥ 4.5:1 (texto normal) / 3:1 (texto grande/UI). **Naranja con texto navy** (no blanco). Navy sobre `#F4F7FB` = 17:1 ✓.
- Estado = color + icono + texto (vía `StatusBadge`).
- Foco de teclado visible (`:focus-visible`), orden lógico, `Sheet/Modal` con foco atrapado y Esc.
- Táctiles ≥ 44×44. Inputs con `label`; errores `role="alert"` + `aria-describedby`.
- `prefers-reduced-motion`: desactiva animaciones no esenciales (pulsos del overlay). Verifica cada superficie **glass** con texto real: si no llega a 4.5:1, sube opacidad del fondo u oscurece el texto.

---

## 7. GUARDARRAÍLES DE INGENIERÍA
- No cambies contratos de API, tipos generados ni lógica de hooks (`use*`). Rediseñas presentación.
- Conserva `data-testid` y roles ARIA. Si cambias microcopy/markup que un test comprueba, **actualiza el test** conservando cobertura (no lo borres). No rompas el test del overlay (`fill="none"`).
- Cada pantalla debe verse bien con sus feature flags en ON y OFF.
- PWA/offline intacto (fuentes/iconos en bundle). Sin peticiones de red en arranque.
- No metas librerías pesadas sin justificar tamaño. Libera `objectURL` como ya se hace.
- Seguridad: mantén `referrerPolicy="no-referrer"` en el logo; nada de `dangerouslySetInnerHTML`; `localStorage` en try/catch.
- Sin regresión en admin (fuera de alcance): ábrelo tras migrar tokens y confirma que no se degrada.

---

## 8. FLUJO DE TRABAJO EN EL VPS + SUBIDA A GITHUB (crítico)

Trabaja de forma **incremental y verificada**. **No subes nada hasta que esté fino y verde.**

**Preparación**
```bash
git status && git branch --show-current            # confirma rama limpia
git checkout feat/autofactu-rollout-r051
git pull --ff-only origin feat/autofactu-rollout-r051
git checkout -b feature/design-system-user-flow    # rama de trabajo
cd frontend && npm ci
```

**Por cada bloque/PR (ver §9):**
1. Implementa el bloque completo.
2. Verifica en local (todo debe pasar):
```bash
cd frontend
npm run lint
npx tsc --noEmit          # o el script de typecheck del repo
npm run test              # vitest: mantener/actualizar tests, verde
npm run build             # build de producción sin errores
```
3. Prueba visual: `npm run dev` y revisa **claro y oscuro** en móvil (390) y escritorio (1024/1440) para las pantallas del bloque.
4. Commit con Conventional Commits en español, referenciando el bloque. Ej.: `feat(frontend): sistema de tokens dual-theme, lucide y toggle de tema (bloque 1)`.
5. Si hay pre-commit/gitleaks, deja que corra; si detecta secreto, **para y no subas**.

**Subida (solo cuando el flujo usuario esté fino y todo verde):**
```bash
git push -u origin feature/design-system-user-flow
# Integración a la rama de trabajo principal (Julio dijo: seguir la rama más avanzada):
git checkout feat/autofactu-rollout-r051
git merge --no-ff feature/design-system-user-flow
git push origin feat/autofactu-rollout-r051     # NUNCA --force; si el remoto rechaza, para y avisa
```
> Julio llevará luego `feat/autofactu-rollout-r051` → `develop` → `main`. Tú no toques `develop`/`main`.

**Reglas duras del git:** nunca `push --force`, ni `reset --hard`, ni reescribir historia. Verifica `.env`/secretos NO suben (`.gitignore`). Si `pull`/`merge` da conflicto, **para y avisa** (ahí se pierde trabajo). Al final, informa: hash subido, `git log --oneline -6`, y confirmación de que remoto y local coinciden.

**Criterio de “fino” antes de subir (Definición de Hecho):**
- [ ] Las 6 pantallas del flujo usuario rediseñadas en Dirección A, claro y oscuro.
- [ ] `lint` + `tsc` + `test` + `build` en verde.
- [ ] AA verificado (contraste, foco, estados con icono+texto), incluido el naranja con texto navy.
- [ ] Funciona con `scanner_v2_enabled`, `continuous_capture_enabled`, `review_inbox_enabled` en ON y OFF.
- [ ] Admin/plataforma sin regresión visual.
- [ ] Sin HEX ni clases `slate/emerald` sueltas en el flujo usuario.

---

## 9. PLAN DE BLOQUES/COMMITS (incremental)
1. **Bloque 1 — Fundamentos:** consolidar tokens `--tn-*`, `--tn-accent-ink` navy, `--tn-accent-strong`, **modo oscuro** + toggle, fuentes auto-hospedadas, `lucide-react`. Sin cambios de pantalla. Capturas claro/oscuro.
2. **Bloque 2 — `src/ui`:** Button, Card, Field, StatusBadge, SegmentedControl, Sheet/Modal, Spinner, EmptyState, Banner, ThemeToggle (+ tests).
3. **Bloque 3 — Shell + navegación usuario (4 destinos) + Login.**
4. **Bloque 4 — Escáner** (idle, overlay, preview, multipágina, errores; sin “Varias facturas”).
5. **Bloque 5 — Subir Archivo** (dropzone, estados por documento, resumen, fallos parciales).
6. **Bloque 6 — Confirmar** (marcas de confianza, verdict CIF, secciones, autosave, aviso nitidez).
7. **Bloque 7 — Pendientes + Historial** (resumen, estados, empty, cargar más; H1 “Pendientes”).
8. **Bloque 8 — Pulido y a11y:** contraste (incl. glass), `prefers-reduced-motion`, responsive 360/390/768/1024/1440, limpieza de clases legacy, capturas antes/después.

Si trabajas desatendido: ejecuta los bloques en orden, verificando cada uno; no subas hasta cumplir la Definición de Hecho.

---

## 10. LO QUE NO DEBES HACER
- ❌ Rediseñar panel/admin/plataforma/supervisión ahora.
- ❌ Cambiar lógica de negocio, endpoints, tipos generados o el motor de escáner.
- ❌ Romper la PWA (fuentes por CDN, red en arranque).
- ❌ Comunicar estado solo por color; usar texto **blanco** sobre naranja.
- ❌ Borrar tests o `data-testid` “para que pase”.
- ❌ Asumir un feature flag activo.
- ❌ `push --force` / reescribir historia / tocar `develop`/`main`.
- ❌ Subir con tests/tsc/build en rojo.

---

## 11. DECISIONES YA CERRADAS POR JULIO (no vuelvas a preguntarlas)
- Dirección visual: **A “Claridad”** (captura móvil cuidada). Paleta marca navy `#021231` + naranja `#FA6703` + fondo `#F4F7FB`.
- **Claro + oscuro** ambos. Iconos **lucide-react**. Tokens semánticos sobre `--tn-*` + acento por tenant (`--color-primary`). Tailwind se mantiene; shadcn no obligatorio (primitivos en `src/ui`).
- **Prioridad flujo usuario**; admin después con el mismo branding.
- **Rama base:** `feat/autofactu-rollout-r051`; luego Julio la pasa a develop/main.
- Panel admin (fase posterior): **paginación backend + virtualización frontend + búsqueda/filtros/ordenación** (ya existe un filtro de facturas; es cosa del admin, no del usuario).
- **A11y AA** obligatorio; **seguridad**: señalar riesgos siempre (CSP y validación de `Content-Type` del logo del tenant se abordan en backend).

---

## 12. CÓMO EMPEZAR (primer paso)
1. Sitúate en `feat/autofactu-rollout-r051`, `npm ci` en `frontend`, y **lee completos** antes de escribir: `index.css`, `tailwind.config.js`, `features/tenancy/theme.ts`, `app/Menu.tsx`, `app/AppRoutes.tsx`, y las 6 pantallas en alcance.
2. Crea la rama de trabajo y ejecuta el **Bloque 1**.
3. Verifica (lint/tsc/test/build) y haz commit. Repite por bloques.
4. Al terminar el flujo usuario y cumplir la Definición de Hecho, **sube** según §8 e informa del resultado (hash, log, coincidencia remoto/local).
5. Tras cada bloque significativo, añade el bloque **🔍 PREGUNTAS DEL EXPERTO** (10–20, por impacto) y responde tú las técnicas; deja para Julio solo las de negocio.

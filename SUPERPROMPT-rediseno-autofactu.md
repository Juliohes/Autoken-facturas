# SUPERPROMPT — Rediseño de branding + navegación inferior + flujo de captura/revisión de Autofactu (Autoken)

> Este documento es la especificación completa y cerrada de una tarea de ingeniería. Está escrito para que la ejecutes de principio a fin sin necesidad de volver a preguntar salvo en los puntos marcados explícitamente como **[PREGUNTAR ANTES DE TOCAR]**. Todo lo demás ya ha sido decidido y verificado contra el código real del repositorio — no lo reinterpretes ni lo simplifiques.

---

## 0. Rol y postura

Actúas como **desarrollador full-stack senior (30+ años), especialista en seguridad (nivel CCN-CERT/INCIBE) y en IA aplicada**. Tolerancia cero al error. No entregues código a medio hacer, sin tipar, sin tests o con `TODO`. Cuando exista una decisión de implementación menor no cubierta aquí explícitamente, resuélvela tú con el mejor criterio profesional — **no preguntes por cosas que un senior de tu nivel decide solo**. Solo debes parar y preguntar en los puntos marcados **[PREGUNTAR ANTES DE TOCAR]**, porque son decisiones de negocio que solo Julio puede tomar y equivocarte ahí tiene coste real (pérdida de datos, romper un flujo en producción, o tocar una pantalla que no debías tocar).

---

## 1. Contexto del proyecto (verificado contra el repositorio real)

- **Repositorio**: `https://github.com/Juliohes/Autoken-facturas` (privado/propiedad de Julio).
- **Rama de partida recomendada**: `feat/autofactu-rollout-r051`. Es la rama más avanzada del frontend: ya incluye "Mis facturas" (bandeja/inbox), captura continua, la pantalla de vista previa "Usar foto / Repetir", flags de features y el endpoint `GET /api/v1/invoices/inbox`. **Antes de escribir una sola línea, confirma en el propio repo cuál es la rama/commit que está realmente desplegado en producción para el subdominio `setex.autoken.es`** (puede que exista un commit posterior no analizado aquí, o hotfixes aplicados directamente). Trabaja siempre a partir del HEAD real de esa rama, no de una copia local desactualizada.
- **⚠️ Discrepancia detectada — verificar antes de empezar**: la pantalla de login que se ve hoy en `https://setex.autoken.es/login` (panel oscuro navy a la izquierda con el claim "Gestiona tus facturas con claridad" + tarjeta blanca de login a la derecha, fondo general gris muy claro) **no coincide con el componente `frontend/src/features/session/LoginScreen.tsx` de ninguna rama inspeccionada** (`develop`, `main`, `experiment/setex-user-ui-v1`, `feat/autofactu-rollout-r051`) — en todas ellas el login es un formulario centrado sobre fondo `bg-slate-900` oscuro, sin panel partido ni claim de marketing. Esto indica que **el frontend en producción ha divergido del repositorio** (un build manual, una rama no listada, o cambios aplicados fuera de git). No asumas que el código que edites en el repo es 1:1 lo que ve el usuario en el login — verifícalo primero y, si hay divergencia, localiza la fuente real antes de tocar nada (pregúntale a Julio dónde vive ese build si no lo encuentras).
- **Stack real (confirmado en `frontend/package.json`)**: React 18.3 + TypeScript + Vite 5 + **TailwindCSS 3.4** (sin librería de componentes, sin Material/Chakra/shadcn) + `react-router-dom` v6 (SPA 100% client-side, `BrowserRouter`, sin recarga de página entre pantallas) + TanStack Query v5 (`@tanstack/react-query`) para todo el fetching + TanStack Table (solo en el panel admin) + `vite-plugin-pwa` (la app es una PWA instalable, respeta `env(safe-area-inset-*)`).
- **Iconos**: no hay ninguna librería de iconos instalada (ni `lucide-react`, ni `heroicons`, ni `react-icons`, ni Font Awesome). Los pocos iconos que existen hoy (hamburguesa, cerrar) son SVG inline hechos a mano con `viewBox="0 0 24 24" stroke="currentColor"`. **Sigue ese mismo patrón**: añade los iconos nuevos (cámara, documento/subir, campana/bandeja de pendientes, reloj/historial, check, alerta, X) como SVG inline propios, trazo simple (`strokeWidth={2}`, `strokeLinecap="round"`, `strokeLinejoin="round"`), sin depender de ningún paquete nuevo. No añadas una dependencia de iconos solo para esto.
- **Backend**: Python + FastAPI, arquitectura por módulos (`identity`, `tenancy`, `invoice_intake`, `invoicing`, `ocr`, `platform_admin`...), RLS multi-tenant a nivel de Postgres, tests exhaustivos con `pytest` (backend) y `vitest` (frontend). El repo tiene su propio flujo de specs por carpetas (`docs/specs/S*.md`, `docs/adr/*.md`) y agentes/skills en `.claude/`. **Sigue esas convenciones**: si el repo tiene una plantilla de spec (`docs/specs/_template.md`) y un ADR template (`docs/adr/0000-template.md`), redacta la spec y el ADR correspondientes a este cambio antes/junto con el código, como se ha hecho en todo el histórico de commits del proyecto. No te saltes ese proceso solo porque este prompt ya es muy detallado.
- **Multi-tenant por subdominio**: cada asesoría (tenant) tiene su propio subdominio (`setex.autoken.es`, y otros como Ilex). El aislamiento entre tenants ya está implementado a nivel de RLS y es **innegociable**: no toques nada de `tenancy/`, tenant resolution o RLS. El theming por tenant (`useTenantTheme`, `AppliedTheme`, `theme.logoUrl`) también ya existe — reutilízalo, no lo reinventes.

---

## 2. Alcance exacto — qué se toca y qué NO se toca

Esto es crítico porque el repo tiene pantallas que a primera vista parecen solaparse. Rutas reales (`frontend/src/app/routes.ts`):

| Ruta | Componente | Rol(es) | ¿Se toca? |
|---|---|---|---|
| `/login` | `LoginScreen` | público | Solo re-tematizar colores (ver §3). Estructura intacta salvo que al verificar el punto de la discrepancia (§1) Julio indique lo contrario. |
| `/capturar` | `CaptureScreen` (dentro de `CaptureRoute`) | `user`, `tenant_admin` | **SÍ — es el corazón de este encargo** (pestaña "Escáner"). |
| `/mis-facturas` | `InvoiceInbox` | `user`, `tenant_admin` | **SÍ** — esta es la pantalla "Mis Facturas" que Julio dice que "deja de tener sentido": se sustituye por la pestaña **Pendientes** (ver §5.3). No la borres sin más: reutiliza su hook `useInvoiceInbox` / endpoint `GET /api/v1/invoices/inbox` como base de datos de la nueva pestaña Pendientes. |
| `/historial` | `InvoiceHistory` | `user`, `tenant_admin` | **SÍ** — se convierte en la pestaña **Historial** (ver §5.4), con el filtro añadido de "solo confirmadas, últimos 4 meses". |
| `/confirmar/:fileId` | `ConfirmationScreen` | `user`, `tenant_admin` | Se seguirá usando tal cual para la revisión real del contenido de la factura (extracción OCR, datos fiscales, envío al tenant). Ese formulario de revisión de campos **no se rediseña** en este encargo — solo cambia CUÁNDO y DESDE DÓNDE se llega a él (ver §5.5). No toques su lógica interna de confirmación/envío. |
| `/facturas` | `InvoicesPanel` | **solo `tenant_admin`** | **NO SE TOCA funcionalmente.** Es el panel de administración con filtro por empresa, edición auditada (S3.3), exportación a Excel (S3.2) y modal de líneas de IVA. No es lo mismo que "Mis Facturas" (`/mis-facturas`) aunque el nombre se parezca — no los confundas ni fusiones. Recolorea solo tokens globales si aplica (§3), nada más. |
| `/empresas` | `CompaniesPanel` | `tenant_admin` | No se toca funcionalmente. Solo tokens de color. |
| `/pendientes-equipo` y `/pendientes-equipo/:fileId` | `PendingSupervisionPanel`, `SupervisionReviewScreen` | `tenant_admin` | No se toca. Es la cola de revisión a nivel de equipo/tenant_admin, un concepto distinto de la pestaña "Pendientes" personal que vas a construir (esa es del usuario individual, alimentada por `/api/v1/invoices/inbox`). |
| `/plataforma/*` | `PlatformTenants`, `PlatformSettings`, `BenchmarkRanking`, `PlatformLab`, `GlobalPendingPanel` | `platform_admin` | No se toca. Fuera de alcance total. |

**Regla de oro del alcance**: el rediseño de navegación inferior (Escáner / Subir Archivo / Pendientes / Historial) y el nuevo comportamiento de captura afectan a las pantallas que usan hoy los roles `user` y `tenant_admin` cuando actúan como "persona que sube y revisa facturas" (`/capturar`, `/mis-facturas`, `/historial`, `/confirmar/:fileId`). **NO toca** el panel de administración de asesoría (`/facturas`, `/empresas`) ni nada de `/plataforma/*` ni `/pendientes-equipo`. Si en algún momento del desarrollo ves que aplicar un cambio "obligaría" a tocar `InvoicesPanel`, `CompaniesPanel` o los paneles de plataforma para que todo cuadre, **para y pregunta a Julio explícitamente antes de tocarlos** — no lo decidas tú.

---

## 3. Branding y sistema de color (global)

### 3.1 Diagnóstico del problema actual (verificado en `frontend/tailwind.config.js` y `frontend/src/app/AppRoutes.tsx`)

El repo ya remapea la paleta de Tailwind con los colores reales de marca — no son colores inventados, son estos:

```js
// frontend/tailwind.config.js — colores REALES de marca ya definidos
colors: {
  slate: {
    100: '#E8EDF5',
    200: '#D3DBE8',
    300: '#B7C3D8',
    400: '#7C8CA8',
    500: '#3A4A66',
    600: '#22314D',
    700: '#16233B', // navy exacto del logotipo
    800: '#101A2E',
    900: '#0B1322',
  },
  emerald: {
    200: '#FFC9A8',
    400: '#FF8A47',
    500: '#FF7A3D',
    600: '#F26522', // naranja de marca
  },
},
```

El problema NO son los colores en sí (el navy `#16233B` y el naranja `#F26522` son correctos, coinciden con el logo que has visto). El problema es **dónde se aplican**: `frontend/src/app/AppRoutes.tsx` envuelve TODO el árbol autenticado en:

```tsx
<div className="min-h-screen bg-slate-900 text-slate-100">
```

Es decir, el fondo dominante de toda la app es `slate-900` (`#0B1322`, casi negro-navy) con texto claro encima — y luego cada pantalla individual reutiliza `slate-800`/`slate-700` como fondo de "tarjetas" dentro de ese fondo oscuro. Resultado: la app entera es oscura, no solo secciones puntuales, y varias combinaciones texto/fondo quedan con contraste insuficiente (el propio código lo reconoce: hay un comentario explícito admitiendo que sin ese `bg-slate-900` en el contenedor raíz "el fondo por defecto es blanco y ese texto queda casi invisible" — es decir, el texto de las pantallas se diseñó dando por hecho fondo oscuro, y es exactamente eso lo que hay que revertir).

### 3.2 Objetivo de color

- **Fondo dominante de toda la app**: claro, no navy. Usa un tono neutro clarísimo (puedes usar `slate-100` (`#E8EDF5`) o un blanco ligeramente cálido `#FAFBFD` como base de página — decide tú el matiz exacto entre esas dos opciones con criterio de diseño, ambas son válidas y coherentes con la marca).
- **Navy del logo (`#16233B` / `slate-700`)**: se conserva pero se usa con moderación — como color de acento oscuro, nunca como fondo general de pantalla. Su uso obligatorio: la barra superior actual (`Menu.tsx`) y la nueva barra inferior de navegación (§4). También válido para textos de alto contraste sobre fondo claro, títulos destacados, o elementos que necesiten "peso" visual puntual.
- **Naranja de marca (`#F26522` / `emerald-600`)**: color de acento/acción principal (botones primarios, estado activo, indicador del bottom nav), en poca cantidad — nunca como fondo de bloques grandes.
- **Blanco**: para tarjetas/paneles sobre el fondo claro dominante, con bordes sutiles (`border-slate-200` o similar) en vez del actual `border-slate-700` (pensado para fondo oscuro).
- **Auditoría obligatoria de contraste**: recorre CADA pantalla dentro del alcance (§2) y localiza cualquier combinación texto/fondo que hoy dependa del fondo oscuro global (p. ej. `text-slate-300`, `text-slate-400` sobre lo que pasará a ser un fondo claro quedarían casi invisibles). Sustitúyelas por tonos oscuros legibles (`text-slate-700`, `text-slate-800`, `text-slate-900` según jerarquía) allí donde el fondo local sea claro, y mantén texto claro (`text-slate-50`/`text-white`) únicamente donde el fondo local siga siendo oscuro (barra superior, barra inferior, botones de acento sobre navy/naranja). No hagas un cambio global ciego de `text-slate-300` → `text-slate-700`: revisa componente a componente, porque algunos siguen teniendo fondo oscuro intencionadamente (las dos barras) y ahí el texto claro debe permanecer.
- **No inventes una paleta nueva de cero.** Reutiliza y extiende la que ya existe en `tailwind.config.js` (añade tonos intermedios si te faltan, p. ej. un `slate-50` clarísimo para el fondo de página si `slate-100` no es suficientemente claro), para no romper los ~150 usos de `slate-*` y 14 de `emerald-*` ya presentes en el código (tal y como el propio comentario del archivo advierte).
- **No es un modo oscuro real ni un toggle de tema.** Confirmado por Julio: fondo claro fijo siempre, sin alternancia. No implementes ningún selector de tema.

### 3.3 Botones que no se ven / anotaciones ilegibles

Además de la auditoría de contraste general del punto anterior, revisa específicamente: badges de estado (`STATUS_LABEL` en `InvoiceHistory.tsx` e `InboxItem.tsx`), mensajes de error (`role="alert"`, hoy `text-red-400` sobre fondo oscuro — sobre fondo claro necesita ajustarse, p. ej. `text-red-700` con fondo `bg-red-50`), el badge de baja nitidez / avisos ámbar (`border-amber-500/60 bg-amber-500/10 text-amber-200` — mismo problema), y los estados `disabled:opacity-40` de los botones (verifica que sigan siendo legibles sobre fondo claro, no solo sobre oscuro).

---

## 4. Barra de navegación inferior (bottom navigation bar)

Aplica **solo** a las pantallas dentro de alcance (`/capturar`, la nueva pantalla "Pendientes", `/historial`) y a los roles `user` y `tenant_admin` cuando navegan por ese flujo. No sustituye el `Menu.tsx` superior para `platform_admin` ni para las secciones de `tenant_admin` fuera de alcance (`/facturas`, `/empresas`) — ahí sigue el menú superior actual (solo re-tematizado en color).

### 4.1 Requisitos de diseño (verbatim de la especificación de Julio, no los relajes)

- Fija en la parte inferior de la pantalla (`position: fixed`, `bottom: 0`), en **móvil**.
- Exactamente **4 botones**, repartidos horizontalmente con el mismo espacio entre ellos (`grid grid-cols-4` o `flex` con `flex: 1 1 0` en cada botón).
- Cada botón: icono simple y moderno (SVG inline, ver §1) + etiqueta de texto corta debajo.
- Botón de la sección activa: icono y texto en el color principal de la app (naranja de marca `#F26522`), más una línea horizontal fina, corta, con bordes ligeramente redondeados, justo encima del icono, como indicador de sección activa.
- Los otros 3 botones: tono neutro y discreto (gris medio, p. ej. `text-slate-500`).
- Diseño minimalista, limpio, moderno, premium. Fondo claro, ligeramente diferenciado del fondo general de la app (p. ej. blanco puro `#FFFFFF` sobre un fondo general `slate-100`, con un `border-top` sutil, sin sombras fuertes ni bordes gruesos).
- Buena separación, alineación y tamaño táctil (mínimo 44×44px de área táctil por botón, estándar de accesibilidad móvil).
- Debe respetar el safe-area inferior del dispositivo: usa `padding-bottom: max(0.5rem, env(safe-area-inset-bottom))`, exactamente el mismo patrón que ya usa `CaptureScreen.tsx` en sus controles de cámara (`pb-[max(1rem,env(safe-area-inset-bottom))]`) — sé consistente con ese patrón existente.
- Animación sutil del indicador activo al cambiar de pestaña (transición CSS de `transform`/`opacity`, ~150–200ms, `ease-out`; nada brusco).
- **No debe alterar ninguna ruta, lógica ni comportamiento de navegación existente más allá de lo descrito en este documento** — es un componente de navegación nuevo, no un cambio de arquitectura de rutas. Añade las rutas nuevas que haga falta (ver §5.3) siguiendo el mismo patrón que ya usa `app/routes.ts` (`ROUTE_DEFS`, `ROUTES`), no un sistema paralelo.

### 4.2 Los 4 botones (orden fijo)

1. **Escáner** → `/capturar` (pantalla existente, rediseñada por dentro según §5).
2. **Subir Archivo** → nueva pantalla/flujo de subida de documentos (§5.2).
3. **Pendientes** → nueva pantalla que sustituye conceptualmente a `/mis-facturas` (§5.3).
4. **Historial** → `/historial` existente, con el filtro nuevo (§5.4).

### 4.3 Versión escritorio

Julio ha confirmado que la app debe convivir con una versión de escritorio adaptada profesionalmente, aunque el uso mayoritario sea móvil. Diseña un breakpoint (`md:` de Tailwind, 768px, coherente con el que ya usa `Menu.tsx` para su propio comportamiento responsive) en el que la bottom nav de 4 botones se transforma en una barra de navegación lateral o superior secundaria para escritorio (tú decides cuál de las dos encaja mejor con el layout actual del `Menu.tsx` superior existente — evalúa ambas opciones y justifica tu elección en la spec/ADR que redactes, pero no dupliques innecesariamente el `Menu.tsx` de arriba: intégralo con él en vez de apilar dos barras de navegación en desktop). Mismos 4 destinos, mismo indicador de sección activa (adaptado a la orientación horizontal/vertical que elijas), mismo criterio minimalista y de marca. No es aceptable que en escritorio la bottom nav móvil simplemente se quede pegada abajo sin adaptar — debe leerse como diseñada específicamente para pantalla grande.

---

## 5. Comportamiento y funcionalidades — pestaña por pestaña

### 5.1 Toggle Recibida / Emitida (aplica a Escáner y a Subir Archivo)

Hoy (`frontend/src/features/capture/CaptureScreen.tsx`, `types.ts`) el tipo es:

```ts
export type Direction = 'recibida' | 'emitida'
```

y el estado inicial es `useState<Direction>('recibida')` — **siempre hay una opción preseleccionada**. Esto cambia:

- Cambia el tipo a `Direction = 'recibida' | 'emitida' | null` (o usa un tipo separado `DirectionSelection` si prefieres no tocar el `Direction` que ya viaja tipado en `useUploadCapture.ts`, `ConfirmationScreen`, `postConfirmNavigation.ts`, etc. — decide tú la forma menos invasiva, pero el resultado observable debe ser el mismo).
- Estado inicial: **sin selección** (`null`), cada vez que se entra a la pantalla Escáner o Subir Archivo.
- El toggle se reposiciona visualmente más cerca del botón "Tomar foto" (hoy vive arriba del todo, separado del bloque de captura — el propio JSX de `CaptureScreen.tsx` lo tiene como primer elemento de la sección, con `space-y-5` genérico respecto al resto).
- **Bloqueo obligatorio**: mientras `direction === null`, los botones "Tomar foto", "Varias hojas" y "Subir archivo" deben estar deshabilitados/bloqueados. Si el usuario pulsa cualquiera de los tres sin haber elegido Recibida/Emitida, se muestra un **toast/snackbar bloqueante** (Julio lo especificó así explícitamente: bloqueante, no solo informativo) con un mensaje del tipo "Elige si la factura es recibida o emitida antes de continuar" y los tres botones permanecen bloqueados hasta que se seleccione una opción. No existe hoy ningún componente de toast/snackbar en el repo (no hay ninguna librería de notificaciones instalada) — constrúyelo como un componente propio reutilizable (`shared/Toast.tsx` o similar, siguiendo la convención de carpeta `frontend/src/shared/` que ya existe con `ScrollableTable.tsx`, `DataTableTh.tsx`), accesible (`role="status"`/`aria-live="assertive"` para el caso bloqueante), consistente con la nueva paleta de marca.
- **Reseteo tras completar una captura**: confirmado por Julio — cada vez que se completa una subida (single, multipágina o desde Subir Archivo), el toggle vuelve a estado sin selección al regresar a la pantalla Escáner. No se resetea solo por navegar fuera y volver sin completar nada (es decir, si el usuario elige "Recibida", sale a Pendientes sin capturar nada, y vuelve a Escáner, la elección de Recibida debe seguir ahí — decide tú si esto lo consigues con estado local que persiste porque el componente no se desmonta, o si necesitas elevar el estado; dado que hoy `CaptureScreen` es un componente montado por ruta y React Router desmonta/remonta al navegar entre rutas distintas, comprueba el comportamiento real: si al salir de `/capturar` y volver se pierde el estado por desmontaje, eso YA cumple el requisito de "resetea salvo que Julio diga lo contrario" — confírmalo con una prueba manual y decide en consecuencia, documentándolo en la spec).

### 5.2 Pestaña "Escáner" (`/capturar`, `CaptureScreen.tsx`)

Estado actual del JSX relevante (confirmado en el código):

```tsx
<div className="flex justify-center">
  <button onClick={() => openCamera()} className="...">Tomar foto</button>
</div>
<div className="flex justify-center gap-3">
  <button onClick={openFilePicker} className="...">Subir archivo</button>
  <button onClick={startMultiplePages} className="...">Varias hojas</button>
</div>
```

Es decir: hoy "Tomar foto" es un círculo grande, y debajo, **en la misma fila** (`flex gap-3`), están "Subir archivo" y "Varias hojas" pegados uno al lado del otro — esto es literalmente lo que Julio describe como "pegado/solapado".

Cambios requeridos:

1. **"Tomar foto"** se mantiene como está (botón circular grande, `onClick={() => openCamera()}`).
2. **"Varias hojas"** pasa a ser un botón **separado, debajo** de "Tomar foto" (su propia fila/bloque, no compartiendo fila con ningún otro botón). Sigue llamando a `startMultiplePages()`, sin tocar su lógica interna.
3. **"Subir archivo"** deja de vivir aquí. Dentro de la pestaña Escáner **ya no aparece** ese botón — su funcionalidad se traslada íntegramente a la nueva pestaña de navegación inferior "Subir Archivo" (§5.3), que es un flujo distinto (PDFs, no fotos de cámara). El botón "Subir archivo" que hoy existe DENTRO del visor de cámara activo (`camera.status !== 'idle'`, para adjuntar una imagen en vez de disparar) es un caso distinto — ese sí se queda donde está, porque forma parte del flujo de captura con cámara abierta, no de la selección inicial. Sé preciso: solo se elimina el botón "Subir archivo" de la pantalla inicial (`camera.status === 'idle'`), no el que aparece dentro de la cámara activa ni el de `MultiPagePanel`.
4. Aplica el reposicionamiento del toggle Recibida/Emitida y el bloqueo descrito en §5.1.
5. **Cambio de comportamiento tras "Usar foto" — el más importante de todo el encargo.**

   Hoy, tras capturar una foto (`handleManualCapture` → `analyzeFrame` → `processCapturedFrame`), se muestra la pantalla `CapturePreview` (`frontend/src/features/capture/CapturePreview.tsx`) con los botones "Repetir" y "Usar foto" — esto ya existe y se queda igual, no lo toques. El problema es lo que pasa DESPUÉS de pulsar "Usar foto" (`confirmPreview()` en `CaptureScreen.tsx`):

   - Hoy: sube el fichero (`uploadBlob`) y, si el `productMode` no es `continuous_invoices`, llama a `onUploaded(uploaded.id, preview.direction, lowSharpness)`. Eso dispara `CaptureRoute` en `frontend/src/app/AppRoutes.tsx`, que guarda ese resultado en el estado `accepted` y renderiza una pantalla intermedia **"Factura aceptada"** con dos enlaces: "Revisar cuando esté lista" (va a `/confirmar/:fileId`) e "Ir a Mis facturas" (va a `/mis-facturas`).
   - **Nuevo comportamiento exigido por Julio**: tras "Usar foto", el sistema **no** muestra ninguna pantalla intermedia y **no** navega a `/confirmar/:fileId` ni a ningún sitio. Sube el fichero en segundo plano (igual que hoy) y **vuelve automáticamente a la pantalla Escáner** en su estado inicial: "Tomar foto" y "Varias hojas" visibles de nuevo, y el toggle Recibida/Emitida **desactivado** (sin selección, según §5.1). La revisión de esa factura ya NO se ofrece aquí — se hace exclusivamente, más tarde, desde la pestaña "Pendientes" (§5.3).
   - Implementación concreta: elimina el estado `accepted` y el bloque JSX de "Factura aceptada" de `CaptureRoute` en `app/AppRoutes.tsx`. Cambia la función `onUploaded` que le pasas a `CaptureScreen` para que, en vez de guardar estado y renderizar otra cosa, simplemente no haga nada visible más allá de lo que ya hace `confirmPreview()` internamente (limpiar `capturedPreview`, `previewStatus`, resetear `direction` a `null`). Si `onUploaded` deja de necesitar navegar a ningún sitio, valora si sigue teniendo sentido como prop o si esa responsabilidad pasa a vivir dentro de `CaptureScreen.tsx` (invalidar la query de `invoice-inbox`/`invoice-history` con TanStack Query para que la pestaña Pendientes se actualice, eso sí es necesario mantenerlo — mira cómo lo hace ya `navigateAfterConfirm` en `confirmation/postConfirmNavigation.ts` con `queryClient.invalidateQueries({ queryKey: INBOX_QUERY_KEY })` y replica ese patrón de invalidación, no la navegación).
   - **Importante**: el modo `productMode === 'continuous_invoices'` (captura continua, ya existente) tiene HOY un comportamiento distinto tras subir — reabre la cámara automáticamente para seguir capturando en vez de volver al menú de Escáner. Decide si ese modo sigue existiendo tal cual (probablemente sí, es un modo explícito distinto que el usuario elige a propósito) o si Julio quiere que también vuelva a la pantalla inicial de Escáner tras cada disparo. **[PREGUNTAR ANTES DE TOCAR]** si no está claro por el contexto — mi lectura es que el modo continuo es una tercera vía ya existente y fuera del alcance de este cambio (no lo menciona en absoluto), así que la opción segura por defecto es dejarlo intacto, pero confírmalo con Julio antes de tocar `continuousCapture.ts` / `acceptContinuousUpload`.
   - El flujo de "Varias hojas" (`sendPages()`, sube vía `/api/v1/uploads/batch`) sigue el mismo criterio: tras enviar, vuelve a Escáner en su estado inicial con el toggle reseteado, sin pantalla intermedia.

### 5.3 Pestaña "Subir Archivo" (nueva)

Reemplaza al botón "Subir archivo" que hoy vive dentro de la pantalla inicial de Escáner (ver §5.2, punto 3). Es un flujo **completamente distinto** al de cámara:

- Accede directamente al selector de documentos del dispositivo (`<input type="file">`), aceptando **tanto imágenes como PDF**, con **PDF como tipo por defecto** — usa el atributo `accept="application/pdf,image/*"` y, si quieres forzar visualmente que el selector nativo abra priorizando PDFs, investiga el soporte real de `accept` en iOS/Android antes de prometer un comportamiento que el propio SO no garantiza (el filtro "por defecto PDF" depende del picker nativo del sistema operativo, no siempre controlable al 100% desde HTML — sé honesto en la implementación sobre esta limitación, no la ocultes).
- Permite **selección múltiple** (`multiple`), con un **máximo de 10 documentos por subida**. Si el usuario selecciona más de 10, bloquea el envío y muestra un aviso claro (reutiliza el mismo componente de toast/aviso bloqueante de §5.1) indicando el límite.
- **Cada documento (PDF o imagen) se trata como una factura independiente**, no como páginas de un mismo documento. Esto es semánticamente distinto del endpoint `POST /api/v1/uploads/batch` que ya existe (ese endpoint agrupa de 2 a 5 imágenes en **una sola** factura multipágina — es lo que usa "Varias hojas"). Para "Subir Archivo" **no reutilices `/uploads/batch`**: cada fichero seleccionado debe generar su propia llamada independiente a `POST /api/v1/uploads` (el endpoint de subida simple), en un bucle/`Promise.allSettled` (no `Promise.all`, para que el fallo de un fichero no tumbe los demás; recopila y muestra qué ficheros fallaron y por qué). Respeta el toggle Recibida/Emitida (§5.1): todos los documentos de esa tanda comparten la misma dirección elegida, igual que hoy comparten `company_id`.
- **Requiere cambio de backend, no es solo frontend.** Verificado en `backend/src/invoice_intake/service.py`: el intake actual solo acepta `image/jpeg` e `image/png` (`mime.sniff_mime(content) not in {"image/jpeg", "image/png"}` → lanza `UnsupportedMediaType` → 415). PDF está **explícitamente bloqueado hoy** en la subida, aunque el motor de OCR interno (`backend/src/ocr/preprocess/rasterize.py::rasterize_pdf`) ya sabe rasterizar un PDF a imágenes — pero solo se usa hoy dentro de algunos extractores OCR (`ocr/engines/azure_openai.py`, `azure_openai_extractor.py`) cuando el contenido almacenado YA es un PDF por otra vía, no para el intake normal de usuario. Tareas de backend necesarias:
  1. Ampliar la validación de `content_type` en `invoice_intake/service.py` (la función que hoy comprueba `content_type not in {"image/jpeg", "image/png"}`) para aceptar también `application/pdf`, aplicando el mismo pipeline de validación de tamaño/antivirus que ya existe para imágenes.
  2. Verificar que el pipeline de OCR completo (no solo el extractor de Azure OpenAI) sabe procesar un `uploaded_file` cuyo `content_type` es `application/pdf` de principio a fin — cuenta de páginas, generación de miniaturas para `GET /uploads/{file_id}/image` y `GET /uploads/{file_id}/pages/{page_number}/image` (mira `_BINARY_DOCUMENT_RESPONSE` en `invoice_intake/router.py`, que ya incluye `application/pdf` en su documentación OpenAPI — indicio de que esto se prevé pero puede no estar completo en todos los motores OCR activos). No des por hecho que basta con tocar la validación del content-type: comprueba motor por motor en `ocr/engines/*` cuáles soportan PDF de entrada hoy y cuáles necesitarían pasar antes por `rasterize_pdf`.
  3. Respeta los límites ya existentes: `max_upload_bytes` (15 MB por fichero, `shared/config.py`), rate limit de `intake_uploads_per_user`/`intake_uploads_per_tenant` (`identity/ratelimit.py::intake_attempt_exceeds`) — con hasta 10 subidas seguidas por acción, verifica que el rate limit actual (20/usuario/60s) no bloquee un uso normal, y ajusta el límite de configuración si hiciera falta, documentando por qué.
- Tras seleccionar y confirmar la subida de los documentos: se suben, quedan pendientes de OCR/revisión (igual que cualquier otra factura), y el usuario **no** pasa por ninguna pantalla de revisión inmediata — igual que en Escáner (§5.2), la revisión se hace después desde "Pendientes". Muestra una confirmación breve no bloqueante (p. ej. "3 documentos subidos, quedan pendientes de revisión") y vuelve a un estado limpio de esta pestaña.
- Aplica también aquí el bloqueo del punto 5.5 (máximo de 10 pendientes totales): si el usuario ya tiene 10 o más facturas pendientes de revisión, el botón/flujo de "Subir Archivo" debe estar bloqueado igual que "Tomar foto" y "Varias hojas".

### 5.4 Pestaña "Pendientes" (nueva — sustituye conceptualmente a `/mis-facturas`)

Base técnica: el endpoint `GET /api/v1/invoices/inbox` ya existe y ya devuelve exactamente lo necesario (`frontend/src/features/inbox/useInvoiceInbox.ts`, `types.ts`):

```ts
InboxOut {
  items: InboxItemOut[]   // cada uno con: id, status, created_at, direction, page_count...
  summary: { processing: number; ready: number; attention: number }
  next_cursor: string | null
}
```

con estados posibles (`STATUS_LABEL` en `InboxItem.tsx`): `pending_ocr`, `processing`, `ocr_done`, `needs_review`, `ocr_failed`, `capture_unreadable`, `confirmed`.

- Reutiliza `useInvoiceInbox` / `invoiceInboxQueryOptions` como fuente de datos de esta pestaña — no crees un endpoint nuevo si este ya cubre el caso (confírmalo leyendo `backend/src/invoicing/router.py` — el endpoint hermano de `/invoices/history` — y su `service`/`repository` correspondiente para `inbox`, que no llegué a inspeccionar línea a línea; verifica tú que ya filtra correctamente por "no confirmadas" o si hoy incluye también las `confirmed` y hace falta añadir el filtro).
- Contenido de la pestaña: lista de todas las facturas **no confirmadas** del usuario (todo lo que hoy muestra `InvoiceInbox.tsx`, pero sin las que ya están `confirmed` — revisa si el backend ya excluye `confirmed` de este endpoint o si hay que añadir el filtro ahí).
- **Icono de alerta (triángulo)** visible en el botón "Pendientes" de la bottom nav cuando `summary` indique 1 o más pendientes reales (decide tú, y documéntalo, si "pendientes reales" = `ready + attention` (los que ya se pueden/deben revisar) o `processing + ready + attention` (todo lo que aún no está confirmado, incluyendo lo que sigue procesándose) — mi recomendación profesional es que el badge cuente `ready + attention` porque son los que requieren acción del usuario AHORA MISMO, mientras que `processing` es solo "en cola, espera" y no debería generar la misma urgencia visual ni contar para el bloqueo de los 10 — pero si Julio prefiere contar el total, es un cambio de una línea, decídelo tú con criterio y dilo explícitamente en la spec que redactes).
- **Badge numérico**: número en blanco (o negro, el que dé más contraste con el rojo elegido) dentro de un círculo rojo sólido, sobresaliendo ligeramente por encima/derecha del icono del botón "Pendientes" en la bottom nav — patrón estándar de "badge de notificación" tipo iOS/Android. Muestra el número exacto de pendientes (con el mismo criterio `ready + attention` u otro que decidas arriba); si son más de 9-10 dígitos visualmente incómodos, usa el patrón habitual "9+" — decide el corte con criterio de diseño.
- **Bloqueo de "demasiados pendientes"**: cuando el contador (mismo criterio que el badge) alcanza **10**, los botones "Tomar foto", "Varias hojas" y "Subir Archivo" quedan bloqueados en toda la app, y al intentar usarlos se muestra un **modal bloqueante** (Julio especificó modal aquí, no toast — distinto del toast de §5.1) con el texto: *"Hay demasiadas facturas pendientes de revisión. Revísalas antes de seguir."* — con un único botón de acción que lleve directamente a la pestaña Pendientes. Implementa el modal como componente propio reutilizable (`shared/Modal.tsx`), con overlay, `role="dialog"` `aria-modal="true"`, cierre con `Esc` y click fuera SOLO si decides que este modal concreto debe poder cerrarse sin ir a Pendientes — dado que Julio lo llama "bloqueante", lo más coherente es que el único cierre posible sea navegar a Pendientes (sin botón de "cancelar" ni cierre por click-fuera), pero usa tu criterio de UX y documenta la decisión.
- Cada ítem pendiente, al pulsarlo, navega a `/confirmar/:fileId` (la pantalla `ConfirmationScreen` existente, sin tocar) — igual que hoy hace `InboxItem.tsx` con sus enlaces "Ver progreso"/"Revisar factura". Reutiliza ese componente o su lógica equivalente.

### 5.5 Pestaña "Historial"

Base: `/historial`, componente `InvoiceHistory.tsx`, hook `useInvoiceHistory.ts`, endpoint `GET /api/v1/invoices/history`.

- **Cambio de contenido**: hoy este endpoint devuelve los últimos envíos **de cualquier estado** (incluye pendientes de OCR, en revisión, fallidos, etc. — mira `STATUS_LABEL` en `InvoiceHistory.tsx`, cubre los mismos 7 estados que el inbox). El requisito nuevo es que Historial muestre **solo las facturas ya revisadas y enviadas al tenant** (`status === 'confirmed'`) de **los últimos 4 meses**.
- **Esto requiere cambio de backend, verificado y no trivial**: en `backend/src/invoicing/repository.py`, la función `list_history()` usa una constante `HISTORY_LIMIT = 20` (sin filtro de estado ni de fecha) — es decir, hoy el backend simplemente devuelve los últimos 20 envíos de cualquier tipo, sin más criterio. Para el nuevo requisito:
  1. Añade un filtro `WHERE f.status = 'confirmed'` (o el nombre de columna/estado real que corresponda — confírmalo contra el modelo, puede que "confirmado y enviado al tenant" viva en la tabla `invoices` en vez de en `uploaded_files.status`; el propio código de `ConfirmationScreen`/`service.confirm()` es la referencia de verdad de qué tabla se actualiza al confirmar).
  2. Añade un filtro de fecha `created_at >= NOW() - INTERVAL '4 months'` (o el campo de fecha que represente el envío/confirmación real, que puede no ser `created_at` de subida sino la fecha de confirmación — verifícalo).
  3. **El límite fijo de `HISTORY_LIMIT = 20` ya no es suficiente**: 4 meses de facturas confirmadas de una empresa activa fácilmente supera 20 registros. Sustituye el límite fijo por paginación real (cursor, igual que ya usa `/api/v1/invoices/inbox` con `next_cursor`/`cursor` — replica ese mismo patrón para consistencia de API en vez de inventar uno nuevo) o, como mínimo, sube el límite a un número que cubra razonablemente 4 meses y añade "cargar más" en el frontend (mismo patrón que ya existe en `InvoiceInbox.tsx` con su botón "Cargar más"). Decide tú cuál de las dos opciones (cursor completo vs. límite alto + cargar más) encaja mejor con el resto de la arquitectura ya existente — mi recomendación es cursor, por consistencia con el inbox y porque evita re-inventar lógica de paginación, pero es una decisión tuya a justificar en la spec.
- El filtro de "últimos 4 meses" lo pidió Julio explícitamente como límite de UX para el usuario normal (no quiere ver más, es demasiado) — el panel de administración (`InvoicesPanel`, fuera de alcance) sigue mostrando el histórico completo sin este límite, no confundas ambos.
- Ítems de Historial: solo lectura, no llevan a `ConfirmationScreen` (ya están confirmados, no hay nada que revisar) — mira si tiene sentido un enlace de "ver detalle" de solo lectura (imagen original vía `GET /uploads/{file_id}/image`, datos confirmados) o si por ahora basta con la lista simple que ya existe. Decide con criterio; no es un requisito explícito de Julio, así que no sobre-construyas si no aporta valor claro.

---

## 6. Menú superior → botón "X" de cierre de sesión

Aplica **solo** al rol `user` (y decide si también a `tenant_admin` cuando navega dentro del flujo Escáner/Pendientes/Historial — dado que ambos roles comparten esas pantallas según `routes.ts`, lo más coherente es que el cambio aplique a ambos roles en ese contexto, no solo a `user`; documenta esta decisión).

- Hoy (`Menu.tsx`): hamburguesa que despliega una lista de enlaces (`menuLinksForRole`) + "Cerrar sesión". Para el rol `user`, `menuLinksForRole` ya devuelve una lista vacía (ningún `ROUTE_DEFS` con `label` incluye el rol `user` salvo `inbox`/`capture`, que además vas a quitar del menú porque ahora viven en la bottom nav) — es decir, el hamburguesa de `user` hoy prácticamente solo sirve para "Cerrar sesión".
- Nuevo comportamiento: sustituye el icono de hamburguesa por un simple icono de **"X"** (mismo SVG que ya existe en `Menu.tsx` para el estado `mobileOpen` — reutilízalo, ya tienes el path `M6 18 18 6M6 6l12 12`), sin desplegable de enlaces (ya no hace falta: Escáner/Subir Archivo/Pendientes/Historial ahora viven en la bottom nav, no en este menú).
- Al pulsar la "X": **pide confirmación** antes de cerrar sesión (confirmado por Julio) — usa el mismo componente `Modal` de §5.3/5.4 con texto tipo "¿Seguro que quieres cerrar sesión?" y dos acciones (Cancelar / Cerrar sesión). Solo al confirmar se ejecuta `logout()` (la función ya existe en `useSession()`, no la toques).
- Para `tenant_admin`, si decides que este cambio también le aplica en el contexto de Escáner/Pendientes/Historial, ten cuidado: `tenant_admin` SÍ tiene enlaces de menú relevantes fuera de este flujo (`Facturas`, `Empresas`, `Pendientes del equipo`) que siguen siendo necesarios — no le quites el acceso a esas rutas. Una opción limpia: la "X" con confirmación de logout aplica dentro de las pantallas del nuevo flujo (Escáner/Subir Archivo/Pendientes/Historial) para ambos roles, mientras que el menú hamburguesa clásico con todos los enlaces se sigue mostrando tal cual en `/facturas`, `/empresas` y el resto de rutas de `tenant_admin`/`platform_admin` fuera de este flujo. Decide la implementación exacta (¿un `Menu` condicional según ruta activa? ¿dos componentes?) con criterio de arquitectura limpia, evitando duplicar lógica de sesión/roles que ya vive en `routes.ts`.

---

## 7. No-negociables (repetido a propósito, por si se te escapa algo entre tanto detalle)

1. **No cambies ninguna ruta, lógica de negocio ni comportamiento de navegación no descrito explícitamente aquí.** El cambio es visual/frontend + los cambios de backend estrictamente necesarios para PDF en "Subir Archivo" (§5.3) y el filtrado/paginación de Historial (§5.5) — nada más de backend.
2. **No toques** `InvoicesPanel`, `CompaniesPanel`, nada de `/plataforma/*`, `PendingSupervisionPanel`/`SupervisionReviewScreen`, tenancy/RLS, ni la lógica de `ConfirmationScreen` (el formulario de revisión de datos de factura en sí).
3. **Actualiza los tests existentes que rompas.** El repo tiene cobertura extensa con `vitest` (frontend) y `pytest` (backend) — hay tests que hoy verifican explícitamente el comportamiento que vas a cambiar (p. ej. `CaptureScreen.test.tsx` probablemente testea que tras "Usar foto" se navega a confirmación; `useUploadCapture.test.ts`, `InvoiceHistory.test.tsx`, `InvoiceInbox.test.tsx` tocan piezas que modificas). No los borres para que pasen: actualízalos para que reflejen el nuevo comportamiento correcto, y añade tests nuevos para cada pieza de comportamiento nueva (toggle sin selección por defecto, bloqueo de botones, badge de pendientes, límite de 10 documentos en Subir Archivo, filtro de 4 meses en Historial, modal de logout, etc.). Sigue el mismo estilo de test ya usado en el repo (Testing Library + Vitest, convención `*.test.tsx`/`*.test.ts` junto al archivo que testean).
4. **Sigue el proceso de documentación del propio repo**: redacta la spec correspondiente en `docs/specs/` (usa `_template.md` como base) y, si la decisión lo amerita (como ya hace el histórico con `docs/adr/000X-*.md`), un ADR para las decisiones de arquitectura no triviales que tomes tú (p. ej. paginación cursor vs. límite alto en Historial, ubicación exacta del bottom nav en el árbol de componentes, forma del tipo `Direction` nullable). Es el patrón que sigue todo el proyecto — no lo omitas por prisa.
5. **Seguridad primero, siempre**: cualquier endpoint nuevo o modificado debe pasar por las mismas guardas de autorización (`require_roles`, comprobación de pertenencia a empresa/tenant) que ya usan `invoice_intake/router.py` e `invoicing/router.py`. No relajes rate limiting ni validación de tipo de fichero al añadir soporte PDF — amplía la lista blanca de content-types, no elimines la comprobación.
6. **Multi-tenant**: nada de lo que construyas debe filtrar datos entre tenants. Todo lo nuevo debe pasar por las mismas dependencias de sesión/tenant (`AuthContext`, RLS) que ya usa el resto del código — no escribas SQL directo que se salte la RLS existente.

---

## 8. Entregable esperado

- PRs/commits siguiendo la convención ya visible en el histórico del repo (`feat(...)`, mensajes descriptivos, referencia a la spec correspondiente).
- Todos los tests (nuevos y existentes) en verde, tanto `npm run test`/`typecheck`/`lint` en `frontend/` como el suite de `pytest` en `backend/` para lo que toques ahí.
- Capturas de pantalla o grabación breve del resultado en móvil (con las 4 pestañas) y en escritorio, para que Julio revise visualmente antes de desplegar.
- Un resumen final explicando, por cada punto marcado con una decisión abierta que hayas tenido que tomar tú (badge de pendientes: qué cuenta exactamente; paginación de Historial: cursor vs. límite+cargar más; alcance de la "X"/logout para `tenant_admin`; qué pasa con `productMode === 'continuous_invoices'`), qué decidiste y por qué — no lo dejes solo implícito en el código.

---

## 9. Preguntas que SÍ debes hacerle a Julio antes de tocar código (no las resuelvas tú)

1. **[PREGUNTAR]** Confirma cuál es el commit/rama realmente desplegado en `setex.autoken.es` hoy — la discrepancia del login (§1) sugiere que el repo inspeccionado no es 100% lo que hay en producción. No empieces a editar sin resolver esto primero, o corres el riesgo de rediseñar una pantalla que luego no es la que se despliega.
2. **[PREGUNTAR]** El modo de captura continua (`productMode === 'continuous_invoices'`, ya existente) — ¿debe seguir reabriendo la cámara automáticamente tras cada disparo (comportamiento actual), o Julio quiere que también vuelva a la pantalla inicial de Escáner como el resto de modos? No lo mencionó explícitamente y no está claro si lo considera parte de este encargo.
3. **[PREGUNTAR]** Los feature flags ya existentes (`continuous_capture_enabled`, `scanner_v2_enabled`, `review_inbox_enabled`) — ¿cuál es su valor actual para el tenant de Setex en producción? Esto determina qué variante de UI ve realmente el usuario final hoy, y por tanto qué punto de partida real tienes.
4. **[PREGUNTAR]** ¿"Historial" debe permitir volver a ver la imagen/documento original de una factura ya confirmada (solo lectura), o basta con la lista simple sin acceso al detalle?
5. **[PREGUNTAR]** Para `tenant_admin`: cuando esté dentro del flujo Escáner/Subir Archivo/Pendientes/Historial con la bottom nav, ¿debe seguir teniendo acceso visible en algún punto a `/facturas`, `/empresas` y `/pendientes-equipo` (su rol de administrador), o esas pantallas quedan accesibles solo navegando fuera de este flujo (p. ej. tecleando la URL o desde algún otro punto de entrada que haya que definir)? Esto condiciona si la "X" de cierre de sesión sustituye del todo su menú de administrador dentro de este flujo o convive con él.

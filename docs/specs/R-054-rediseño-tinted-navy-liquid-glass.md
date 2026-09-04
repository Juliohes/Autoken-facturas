# Spec: R-054 Rediseño visual Tinted Navy Liquid Glass

> Spec-Driven Domain. Esta spec adapta el prompt visual a la aplicación React existente. Solo afecta a
> presentación y experiencia visual. No cambia contratos, lógica de negocio ni permisos.

- **ID / tarea:** R-054
- **Contexto (módulo):** frontend app-shell, captura, revisión, bandejas y paneles administrativos
- **ADR relacionados:** ADR-0001 (RLS y aislamiento por tenant), ADR-0014 (white-label por tenant)
- **Estado:** aprobada por Julio (2026-08-28)

## 1. Problema y valor de dominio

La aplicación necesita una experiencia visual más clara, cuidada y profesional para móvil y escritorio,
manteniendo todas las funciones actuales de facturación. El estilo objetivo es una interfaz clara con
superficies sólidas para datos y controles de navegación/acción con cristal azul marino profundo.

## 2. Lenguaje ubicuo

- **Tinted Navy Liquid Glass:** superficie interactiva azul marino opaca, con transparencia moderada,
  borde cian, reflejo interior y sombra suave.
- **Shell autenticado:** contenedor común de la aplicación una vez iniciada la sesión.
- **Navegación superior:** barra actual con sus enlaces y acciones según rol; se conserva como única navegación.
- **Experiencia de captura:** pantalla y controles usados para tomar, revisar y enviar una foto.
- **Panel administrativo:** facturas, empresas, pendientes tenant, plataforma, laboratorio y métricas.
- **Superficie de datos:** tarjetas, formularios, tablas y desgloses donde la legibilidad tiene prioridad;
  permanece sólida y clara, no de cristal.

## 3. Comportamientos (criterios de aceptación)

### C1 — El shell autenticado adopta el estilo visual nuevo
- **Given** una persona autenticada accede a la aplicación.
- **When** se muestra cualquier pantalla permitida.
- **Then** el contenido usa fondo claro, tipografía legible, jerarquía visual consistente y los tokens
  Tinted Navy Liquid Glass sin alterar sus elementos funcionales.

### C2 — La navegación superior conserva sus funciones
- **Given** existe una sesión con cualquier rol actual.
- **When** se muestra la barra superior.
- **Then** conserva el mismo número de enlaces, textos, permisos, destinos y acciones, pero puede cambiar
  su posición interna, color, estados visuales y estilo para integrarse en el nuevo sistema.

### C3 — La captura tiene una experiencia visual común
- **Given** una persona con permiso actual para capturar entra en `Subir factura`.
- **When** usa la pantalla de captura, la vista previa o los controles de cámara.
- **Then** ve la misma composición y lenguaje visual profesional que el resto de usuarios con permiso,
  conservando los controles y funciones actuales, incluido el selector de empresa cuando el rol lo necesita.

### C4 — Los paneles administrativos comparten lenguaje visual
- **Given** un `tenant_admin`, `admin-tech` o `platform_admin` accede a un panel autorizado.
- **When** se muestra el panel correspondiente.
- **Then** utiliza la misma paleta, tipografía, superficies, estados y tratamiento de controles, respetando
  la visibilidad y las acciones que ya tenía ese rol.

### C5 — El cristal se limita a navegación y acciones
- **Given** se muestra un control interactivo o una agrupación de acciones existente.
- **When** se aplica el tema visual.
- **Then** puede usar Tinted Navy Liquid Glass con fallback sólido y estados de foco/hover/active visibles.
- **And** las tablas, listas, formularios, importes, desgloses fiscales y textos largos permanecen sobre
  superficies sólidas para maximizar la legibilidad.

### C6 — La cámara conserva contraste y funcionamiento
- **Given** se abre la vista de cámara.
- **When** la persona encuadra, ilumina, captura o repite una foto.
- **Then** la superficie de cámara conserva el fondo oscuro, los textos y controles legibles y toda la
  lógica actual de captura, análisis, fallback y preview.

### C7 — El tema funciona en móvil, escritorio y sin filtros de cristal
- **Given** el navegador mide entre 320 px y escritorio, o no soporta `backdrop-filter`.
- **When** se carga cualquier pantalla.
- **Then** no aparece scroll horizontal, los controles conservan objetivos táctiles utilizables y el tema
  usa una superficie opaca equivalente sin bloquear la interacción.

### C8 — Accesibilidad y estados mantienen su significado
- **Given** se usa teclado, lector de pantalla, zoom, movimiento reducido, contraste aumentado o forced colors.
- **When** se navega o interactúa con la aplicación.
- **Then** se mantienen foco visible, nombres accesibles, contraste AA, estados no basados solo en color y
  los atributos ARIA existentes.

## 4. Invariantes y reglas de negocio

- No se modifican backend, contratos API, nombres de campos, autenticación, almacenamiento, estado de negocio,
  rutas, permisos, validaciones ni navegación funcional.
- Se conserva exactamente el número y significado de los botones y acciones existentes; se permite cambiar
  únicamente su presentación, posición visual y estilo.
- La navegación superior permanece como única navegación; no se añade navegación inferior.
- No se añade captura a `platform_admin` si no la tenía antes.
- El theming dinámico del tenant conserva su color primario en las acciones que ya lo utilizaban.
- Éxito, advertencia, error, borrador y duplicado mantienen diferencias comprensibles además del color.
- La cámara conserva fondo oscuro y contraste alto aunque el shell sea claro.

## 5. Casos límite y errores

- Sin soporte de `backdrop-filter`, el cristal se degrada a una superficie navy opaca equivalente.
- Con `prefers-reduced-motion`, se reducen transiciones y animaciones sin ocultar estados.
- Con `prefers-contrast: more` o `forced-colors: active`, aumentan los bordes y se conserva la interacción.
- En nombres largos, importes grandes, tablas y formularios, no se sacrifica legibilidad por el efecto visual.
- En tenants sin branding propio, se usa la paleta Tinted Navy por defecto y el acento oficial existente.

## 6. Fuera de alcance (no-objetivos)

- No se añade todavía **Seguir subiendo facturas** ni se modifica el aviso de factura eliminada.
- No se crea navegación inferior ni nuevos destinos.
- No se reescribe el frontend ni se migra de React/Tailwind.
- No se copian páginas paralelas, CSS vanilla, Tabulator ni lógica del repositorio antiguo.
- No se añaden dependencias visuales pesadas ni efectos WebGL/SVG que no sean necesarios.
- No se cambian funcionalidades de captura, revisión, OCR, duplicados, borrado, formularios o paneles.

## 7. Notas de verificación

- Frontend: suite existente, typecheck, lint y build.
- Responsive: anchos 320, 360, 390, 430, 768 y escritorio; sin scroll horizontal.
- Accesibilidad: teclado, foco, zoom 200 %, reduced motion, contraste aumentado y fallback sin blur.
- Revisión visual de captura, preview, bandeja, confirmación, panel tenant y panel tech/platform.
- El diff funcional debe demostrar que no cambian rutas, llamadas API, permisos ni contratos.

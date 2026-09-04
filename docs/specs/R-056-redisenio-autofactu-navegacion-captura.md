# Spec: R-056 Rediseño de Autofactu, navegación y flujo de captura

> Spec-Driven Domain. Esta spec es la fuente única que alimenta los tests y la implementación.

- **ID / tarea:** R-056
- **Contexto (módulo):** frontend/app, capture, inbox, history, invoice_intake
- **ADR relacionados:** ADR-0021
- **Estado:** implementada

## 1. Problema y valor de dominio

La persona que sube facturas necesita un flujo móvil y de escritorio claro: entrar por Escáner, subir archivos
independientes, revisar lo pendiente y consultar únicamente el histórico confirmado. La navegación actual mezcla
acciones de captura, bandeja e histórico y obliga a revisar una factura inmediatamente después de capturarla.

## 2. Lenguaje ubicuo

- **Escáner:** captura de una factura mediante cámara; permite una foto o varias hojas de una misma factura.
- **Subir Archivo:** selección de hasta diez documentos independientes, imágenes o PDF, que se envían como facturas
  separadas.
- **Pendiente:** factura del usuario que todavía no está confirmada, incluidos estados de procesamiento y revisión.
- **Pendiente accionable:** factura en estado `ocr_done`, `needs_review`, `ocr_failed` o `capture_unreadable`.
- **Historial:** facturas confirmadas y enviadas al tenant durante los últimos cuatro meses.
- **Dirección:** `recibida` o `emitida`; es obligatoria antes de iniciar una captura o subida.
- **Captura continua:** flujo existente de varias facturas consecutivas. Esta tarea elimina su botón visible y no
  cambia su lógica interna sin una decisión posterior expresa.

## 3. Comportamientos (criterios de aceptación)

### C1 — Navegación del usuario
- **Given** una sesión de rol `user` en Escáner, Pendientes o Historial
- **When** se muestra la aplicación en móvil
- **Then** aparece una barra inferior fija con exactamente cuatro destinos, en este orden: Escáner, Subir Archivo,
  Pendientes e Historial, con icono, texto, objetivos táctiles mínimos de 44 px y safe area inferior.

### C2 — Navegación de escritorio y administrador separado
- **Given** una sesión de rol `user` en una ventana de al menos 768 px
- **When** se muestra la aplicación
- **Then** la navegación de las cuatro secciones se adapta a escritorio sin quedarse pegada al borde inferior.
- **Given** una sesión `tenant_admin` o `platform_admin`
- **When** se muestra el panel administrativo
- **Then** conserva su menú administrativo separado y no recibe la navegación inferior del flujo de usuario.

### C3 — Dirección obligatoria
- **Given** que la persona entra en Escáner o Subir Archivo
- **When** todavía no ha elegido Recibida o Emitida
- **Then** ambas opciones aparecen sin seleccionar y las acciones de captura/subida están bloqueadas.
- **When** intenta continuar mediante una acción bloqueada
- **Then** aparece un aviso accesible y persistente indicando que debe elegir la dirección.

### C4 — Escáner sin subida inicial ni captura continua visible
- **Given** la pantalla Escáner sin cámara abierta
- **When** la persona la consulta
- **Then** muestra Tomar foto y Varias hojas; no muestra Subir archivo ni el botón de Varias facturas.
- **Given** la cámara abierta
- **Then** conserva la captura, el visor, Automático/Manual, linterna y Cerrar cámara sin alterar su lógica.

### C5 — Captura y regreso limpio
- **Given** una foto capturada y revisada con Usar foto
- **When** la subida simple termina correctamente
- **Then** no aparece una pantalla intermedia ni navega a confirmación; vuelve al Escáner limpio y la dirección queda sin
  seleccionar.
- **Given** una factura de varias hojas enviada correctamente
- **Then** vuelve al Escáner limpio y la dirección queda sin seleccionar.
- **Given** captura continua existente
- **Then** no se modifica su comportamiento interno en esta tarea.

### C6 — Subir Archivo independiente
- **Given** una dirección seleccionada en Subir Archivo
- **When** se abre el selector
- **Then** acepta `application/pdf,image/*` y selección múltiple.
- **When** se seleccionan entre uno y diez documentos
- **Then** cada documento se envía como una factura independiente mediante el flujo de subida simple.
- **When** se seleccionan más de diez
- **Then** se bloquea el envío y se muestra un aviso accesible con el límite.
- **When** termina la tanda
- **Then** los documentos quedan pendientes de OCR/revisión, aparece una confirmación no bloqueante y la pantalla
  queda limpia sin navegar a revisión.

### C7 — Pendientes
- **Given** una persona autenticada
- **When** entra en Pendientes
- **Then** ve sus facturas no confirmadas usando la fuente de datos de inbox y ningún registro confirmado.
- **When** pulsa un pendiente
- **Then** navega a la pantalla existente de confirmación de ese fichero.
- **Given** al menos un pendiente accionable
- **Then** el destino Pendientes muestra un indicador de alerta y un badge numérico; el número cuenta `ready + attention`
  y se muestra como `9+` cuando supera nueve.

### C8 — Límite de pendientes
- **Given** diez o más pendientes accionables
- **When** intenta Tomar foto, Varias hojas o Subir Archivo
- **Then** la acción queda bloqueada y aparece un modal bloqueante con el texto “Hay demasiadas facturas pendientes de
  revisión. Revísalas antes de seguir.” y una única acción para ir a Pendientes.

### C9 — Historial confirmado
- **Given** facturas del usuario en distintos estados y fechas
- **When** entra en Historial
- **Then** solo ve facturas `confirmed` de los últimos cuatro meses, en modo solo lectura.
- **When** existen más resultados que la primera página
- **Then** puede cargar la página siguiente sin perder filtros ni mezclar facturas de otros tenants.

### C10 — Cierre de sesión
- **Given** una persona `user` en el flujo de usuario
- **When** pulsa el botón X de la cabecera
- **Then** aparece confirmación accesible con Cancelar y Cerrar sesión.
- **When** confirma
- **Then** se ejecuta el cierre de sesión existente; al cancelar, la sesión permanece activa.
- **Given** un administrador
- **Then** conserva su menú administrativo separado y su cierre de sesión actual.

### C11 — Branding y accesibilidad visual
- **Given** cualquier pantalla incluida en el alcance visual
- **When** se renderiza en móvil o escritorio
- **Then** usa fondo claro `#F4F7FB`, superficies claras, navy `#021231`, naranja `#FA6703`, contraste AA, foco visible,
  objetivos táctiles mínimos y no genera scroll horizontal.
- **Given** un navegador sin `backdrop-filter`
- **Then** las superficies glass se degradan a fondos sólidos legibles.

## 4. Invariantes y reglas de negocio

- La revisión OCR y confirmación existente no se rediseña ni se salta cuando se accede desde Pendientes.
- Una subida de Subir Archivo nunca usa el endpoint de lote de páginas.
- Un documento seleccionado equivale a una factura independiente.
- Ninguna operación cruza el tenant ni el usuario propietario.
- El límite de diez documentos se valida antes de enviar.
- Los fallos individuales de una tanda no cancelan las demás subidas; se informa de cada fallo.
- No se inventan valores OCR: campo no legible continúa siendo `null` con su aviso existente.
- La captura continua se conserva internamente y no se reinterpreta en esta tarea.
- `InvoicesPanel`, `CompaniesPanel`, `/plataforma/*`, supervisión de equipo, tenancy/RLS y el formulario de
  `ConfirmationScreen` quedan fuera del cambio funcional.

## 5. Casos límite y errores

- Dirección ausente, empresa no seleccionada o usuario sin empresa.
- Selector cancelado, fichero vacío, tipo no soportado, PDF corrupto o fichero superior a 15 MB.
- Más de diez documentos, fallo parcial de subida, rate limit y pérdida de red.
- Inbox vacío, endpoint paginado con cursor inválido, historial sin confirmadas y fechas exactamente en el límite de
  cuatro meses.
- Badge sin pendientes accionables, contador superior a nueve y estados de procesamiento que no deben bloquear.
- Usuario con `review_inbox_enabled` desactivado: se conserva la variante existente del flag sin ocultar rutas
  protegidas.
- Viewport móvil con safe area, viewport de escritorio ancho y navegación por teclado.

## 6. Fuera de alcance (no-objetivos)

- No se modifica el formulario de revisión, OCR, detección de documentos ni captura continua interna.
- No se fusionan los paneles administrativos con el flujo de usuario.
- No se añade detalle de imagen al Historial.
- No se crean rutas paralelas ni se cambia el contrato de autorización multi-tenant.
- Los cambios backend se limitan a aceptar/procesar PDF en la subida simple y a filtrar/paginar Historial; no se toca
  RLS ni tenancy.

## 7. Notas de verificación

- Frontend: Vitest + Testing Library para navegación, dirección, bloqueos, subida múltiple, badge, modal y regresiones.
- Backend: pytest para MIME PDF, procesamiento, filtros de historial, cursor, rate limit y aislamiento.
- Build: `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`.
- Verificación manual: viewport móvil y escritorio, teclado, lector de pantalla, selector de PDF/imagen y usuario
  administrador separado.

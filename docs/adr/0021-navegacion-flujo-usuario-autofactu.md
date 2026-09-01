# ADR-0021: Navegación separada para el flujo de usuario de Autofactu

- **Estado**: aceptado
- **Fecha**: 2026-08-31
- **Decisores**: Julio (+ Claude Code)

## Contexto

El producto tiene dos conceptos distintos: el flujo diario de una persona que captura y revisa sus facturas, y el
panel administrativo de un `tenant_admin`/`platform_admin`. Mezclarlos en una única navegación hace que las acciones
de usuario queden ocultas y que el administrador vea opciones que no corresponden a su panel.

El flujo de usuario necesita cuatro destinos estables: Escáner, Subir Archivo, Pendientes e Historial. En escritorio
no debe parecer una barra móvil pegada al borde inferior. Historial también necesita una consulta acotada y paginada,
mientras que Pendientes necesita un contador accionable para limitar nuevas entradas.

## Decisión

- Mantener el `Menu` administrativo para administradores y no mostrarles la navegación inferior del flujo de usuario.
- Crear una navegación propia para el rol `user`, fija en móvil y adaptada como barra secundaria superior en escritorio.
- Reutilizar las rutas existentes `/capturar`, `/mis-facturas` y `/historial`; añadir solo la ruta de Subir Archivo si no
  existe una equivalente.
- Reutilizar el inbox existente como fuente de Pendientes y añadir el filtro/paginación de Historial en su módulo actual.
- Contar como accionables `ready + attention`, no `processing`: solo bloquean nuevas entradas las facturas que requieren
  intervención actual.
- Usar modal bloqueante para el límite de diez pendientes y toast accesible para dirección ausente.
- Mantener el formulario de confirmación y los controles de autorización existentes.

## Alternativas consideradas

- **Una única barra para todos los roles:** descartada porque mezcla el panel administrativo con el flujo de usuario.
- **Dejar la barra inferior también en escritorio:** descartada porque no ofrece una adaptación profesional a pantallas
  grandes.
- **Contar también `processing` en el badge y bloqueo:** descartada porque una factura en cola no requiere acción
  inmediata y produciría bloqueos prematuros.
- **Límite fijo alto en Historial:** descartado frente a cursor/paginación, que evita truncar datos de cuatro meses.

## Consecuencias

- El usuario tiene una navegación constante y predecible, con separación clara de tareas pendientes.
- El administrador conserva sus accesos y no se modifica su panel funcional.
- Se añade coordinación entre la consulta de inbox, el badge y los bloqueos de captura.
- La paginación requiere ampliar el contrato de Historial y sus pruebas de aislamiento.
- PDF requiere validar MIME, antivirus, tamaño y procesamiento OCR sin relajar seguridad ni rate limiting.

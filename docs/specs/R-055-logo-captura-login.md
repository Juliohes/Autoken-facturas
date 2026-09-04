# Spec: R-055 Integración de marca, captura y visibilidad de contraseña

> Spec-Driven Domain. Esta spec es la fuente única que alimenta los tests y las auditorías.

- **ID / tarea:** R-055
- **Contexto (módulo):** frontend app-shell, tenancy, captura y sesión
- **ADR relacionados:** ADR-0014 (white-label por tenant)
- **Estado:** aprobada por Julio

## 1. Problema y valor de dominio

El logo de Autofactu debe integrarse con la barra o panel donde aparece sin crear un rectángulo propio: el
fondo del archivo del logo será transparente y el azul glass de la superficie se verá detrás de la marca.
Además, la pantalla de captura ya ofrece el acceso al historial mediante la aplicación y no necesita un
botón adicional, mientras que el login debe permitir comprobar la contraseña escrita sin mostrarla por
defecto.

## 2. Lenguaje ubicuo

- **Azul de marca:** `#021232`, el azul de referencia de las superficies navy glass.
- **Superficie del logo:** barra, panel o contenedor inmediato que aloja el logo.
- **Mostrar contraseña:** acción temporal que cambia la representación visual del campo, sin cambiar su
  valor ni el dato enviado al servidor.
- **Usuario:** cualquier rol autenticado o pendiente de autenticación, incluidos `user`, `tenant_admin`,
  `admin-tech` y `platform_admin`.

## 3. Comportamientos (criterios de aceptación)

### C1 — El logo deja ver la superficie glass
- **Given** se muestra el logo Autofactu en el login o en la navegación autenticada.
- **When** se renderiza el logo junto a su superficie inmediata.
- **Then** el archivo del logo tiene fondo transparente fuera de la marca.
- **And** el azul glass de la superficie se ve detrás del logo, sin un rectángulo azul sólido propio.
- **And** esta regla se mantiene en cada ubicación donde se muestra el logo.
- **And** el favicon del navegador y los iconos cuadrados de la PWA usan el símbolo oficial con fondo
  azul sólido, separado del lockup transparente.

### C2 — La captura no muestra un enlace redundante al historial
- **Given** una persona con permiso de captura está en la pantalla para subir facturas.
- **When** la pantalla está lista para tomar o subir una foto.
- **Then** no se muestra el botón o enlace `Ver historial` / `Mis facturas` dentro de esa pantalla.
- **And** las acciones de captura y subida permanecen disponibles sin cambiar su funcionamiento.

### C3 — La contraseña permanece oculta por defecto
- **Given** cualquier persona abre el formulario de inicio de sesión.
- **When** escribe una contraseña sin pulsar el control de visibilidad.
- **Then** el campo usa representación de contraseña oculta.
- **And** se muestra un control accesible para mostrarla temporalmente.

### C4 — El control de visibilidad alterna la contraseña sin alterar el envío
- **Given** una persona ha escrito una contraseña en el login.
- **When** pulsa `Mostrar contraseña`.
- **Then** el texto se muestra y el control pasa a indicar `Ocultar contraseña`.
- **When** pulsa `Ocultar contraseña`.
- **Then** el texto vuelve a ocultarse y conserva exactamente el mismo valor.
- **And** el envío usa la contraseña original, independientemente de cuántas veces se alterne la visibilidad.

## 4. Invariantes y reglas de negocio

- La contraseña nunca se muestra por defecto.
- El control de visibilidad es solo local y no persiste el estado entre cargas del login.
- Ningún cambio visual modifica autenticación, roles, permisos, rutas o contratos API.
- El logo personalizado de un tenant conserva su URL y su branding; la unificación de color aplica a la
  marca Autofactu y a sus superficies contenedoras.
- El color de referencia de las superficies navy glass es `#021232`; el archivo del logo no debe forzar ese
  color en sus píxeles transparentes.
- El lockup completo y transparente solo se usa dentro de la aplicación; el favicon y los iconos PWA no usan
  ese lockup completo.

## 5. Casos límite y errores

- Si el logo no existe o falla su carga, se conserva el fallback actual y no se bloquea el login ni la
  navegación.
- El control de visibilidad debe seguir siendo usable con teclado, lector de pantalla y pantallas táctiles.
- El control no debe enviar un formulario ni borrar el texto escrito.
- En pantallas estrechas, el control de visibilidad no debe provocar scroll horizontal.

## 6. Fuera de alcance (no-objetivos)

- No se cambia la contraseña, la política de seguridad ni la duración de la sesión.
- No se modifica el historial ni se elimina su ruta; solo se retira el acceso redundante desde captura.
- No se rediseñan las imágenes de logos personalizados de tenants ni se les elimina un fondo que no sea el
  asset oficial de Autofactu.
- No se añaden nuevas funciones de navegación.

## 7. Notas de verificación (cómo se prueba de extremo a extremo)

- Tests de comportamiento de login: estado inicial oculto, alternancia visible/oculta y envío del valor
  original.
- Test de comportamiento de captura: ausencia del enlace de historial y presencia de las acciones de captura.
- Inspección del DOM y de los estilos computados del login y la navegación: logo y superficie con
  `#021232` exacto.
- Suite frontend, typecheck, lint y build; revisión responsive en móvil y escritorio.

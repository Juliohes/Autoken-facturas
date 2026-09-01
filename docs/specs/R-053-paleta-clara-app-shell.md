# Spec: R-053 Paleta clara del app shell

> Spec-Driven Domain. Esta spec limita la tarea a colores. No se cambian botones, textos, rutas,
> estados, tamaños, espaciados, estructura, permisos ni funcionalidades.

- **ID / tarea:** R-053
- **Contexto (módulo):** frontend app-shell, captura y paneles autenticados
- **ADR relacionados:** ADR-0001 (RLS y aislamiento por tenant), ADR-0014 (white-label por tenant)
- **Estado:** aprobada por Julio (2026-08-27)

## 1. Problema y valor de dominio

La aplicación funciona, pero las pantallas autenticadas tienen un fondo oscuro que dificulta la lectura
de formularios, tarjetas y tablas. Se necesita una paleta clara, profesional y cálida, inspirada en el
frontend anterior de Setex, sin perder el contraste de la captura de cámara ni la barra superior actual.

## 2. Lenguaje ubicuo

- **Contenido autenticado:** zona de la aplicación que aparece debajo de la barra superior tras iniciar sesión.
- **Barra superior:** menú principal actual, que conserva su fondo oscuro.
- **Paleta clara:** fondo crema suave, superficies blancas, texto azul marino/gris y acento naranja Setex.
- **Panel tenant:** pantallas de facturas, empresas y pendientes del equipo.
- **Panel tech-admin:** pantallas de plataforma y laboratorio disponibles para administración técnica.
- **Superficie de cámara:** vista de encuadre a pantalla completa, que conserva fondo oscuro para favorecer
  la visibilidad de la factura.

## 3. Comportamientos (criterios de aceptación)

### C1 — El contenido autenticado usa la paleta clara
- **Given** una persona autenticada entra en cualquier pantalla de la aplicación.
- **When** se muestra el contenido debajo de la barra superior.
- **Then** el fondo general es crema claro, las superficies son blancas o crema y el texto principal tiene
  contraste oscuro legible.

### C2 — La barra superior conserva su aspecto oscuro
- **Given** la persona está autenticada en cualquier rol permitido.
- **When** se muestra la barra superior.
- **Then** conserva el fondo oscuro y el contraste claro de sus enlaces, logo y acciones.

### C3 — La captura conserva la superficie oscura de cámara
- **Given** la persona abre la cámara desde la pantalla de captura.
- **When** aparece la vista de encuadre.
- **Then** la superficie de cámara sigue siendo oscura y sus textos y controles siguen siendo legibles.

### C4 — La paleta se aplica a todos los paneles administrativos
- **Given** un `tenant_admin` o `admin-tech` abre un panel autorizado.
- **When** se muestra el contenido del panel.
- **Then** usa la paleta clara, manteniendo la barra superior oscura y sin alterar las funciones existentes.

### C5 — El branding dinámico mantiene su acento
- **Given** existe un color primario configurado para el tenant.
- **When** se muestran acciones que ya usan el color primario.
- **Then** siguen usando el acento dinámico del tenant; la paleta clara no elimina el theming existente.

## 4. Invariantes y reglas de negocio

- No se modifica ningún botón, texto, ruta, flujo, estado, tamaño, espaciado o permiso.
- No se modifica la autorización: la captura mantiene el acceso actual de `user` y `tenant_admin`; no se
  añade captura a `platform_admin`.
- El contenido de la cámara mantiene contraste oscuro aunque el resto de la pantalla sea clara.
- El cambio afecta por igual a todos los tenants y usuarios que ya pueden acceder a cada pantalla.
- No se cambian colores de datos que expresan estados de negocio de forma que se confundan entre sí:
  éxito, advertencia, error y duplicado conservan su significado visual.

## 5. Casos límite y errores

- Si no existe branding del tenant, se usa la paleta clara por defecto y el acento naranja Setex.
- En pantallas estrechas, la paleta no debe introducir desbordamiento ni cambiar el comportamiento responsive.
- Los overlays y modales conservan el contraste necesario para leer su contenido.

## 6. Fuera de alcance (no-objetivos)

- No se añade todavía **Seguir subiendo facturas**; queda para una tarea posterior.
- No se rediseña la composición visual, jerarquía, tarjetas, botones, iconos, tipografías ni layout.
- No se corrige en esta tarea el mensaje efímero de factura eliminada.
- No se añade soporte para que `platform_admin` capture facturas.
- No se porta CSS, Tabulator ni código vanilla del repositorio anterior; solo se adapta la paleta existente
  en el frontend React/Tailwind.

## 7. Notas de verificación

- Tests de comportamiento comprobarán que las pantallas autenticadas mantienen sus elementos y aplican las
  clases/estilos de paleta clara.
- `npm test`, `npm run typecheck`, `npm run lint` y `npm run build` deben pasar.
- Se revisarán visualmente `/capturar`, `/mis-facturas`, `/facturas`, `/empresas`, `/pendientes-equipo`,
  `/plataforma`, `/ajustes`, `/ranking-ocr`, `/laboratorio` y `/pendientes-globales` sin modificar sus
  acciones.

# PROMPT MAESTRO - REDISENO COMPLETO FRONTEND "TINTED NAVY LIQUID GLASS"

Actua como un equipo senior especializado en:

* Diseno de producto movil.
* UI/UX para aplicaciones financieras.
* Frontend responsive.
* PWA.
* Accesibilidad WCAG 2.2.
* Sistemas de diseno.
* CSS moderno.
* Integracion visual de marcas.
* Pruebas visuales y funcionales.

Tu mision es redisenar completamente la experiencia visual del frontend de esta aplicacion de facturacion
utilizando el estilo:

# Tinted Navy Liquid Glass

Debes aplicar el nuevo diseno a todas las pantallas del frontend, incluyendo obligatoriamente:

* Login.
* Registro, si existe.
* Recuperacion de contrasena.
* Verificacion o activacion de cuenta.
* Inicio.
* Listado de facturas.
* Creacion de factura.
* Edicion de factura.
* Revision.
* Vista previa.
* Confirmacion.
* Detalle de factura.
* Clientes.
* Productos o conceptos.
* Perfil.
* Configuracion.
* Notificaciones.
* Menus.
* Modales.
* Estados vacios.
* Estados de carga.
* Estados de error.
* Pantallas sin conexion, si existen.
* Cualquier otra ruta o pantalla real del frontend.

---

# 1. RESTRICCION ABSOLUTA

Este trabajo es exclusivamente de:

* Frontend.
* Diseno visual.
* Experiencia de usuario.
* Responsive.
* Accesibilidad.
* Microinteracciones visuales.

No modifiques bajo ningun concepto:

* Backend.
* Base de datos.
* Modelos de datos.
* Migraciones.
* Endpoints.
* Contratos de API.
* Autenticacion del servidor.
* Permisos.
* Roles.
* Logica fiscal.
* Verifactu.
* OCR.
* Procesamiento de facturas.
* Colas.
* Workers.
* Almacenamiento.
* Infraestructura.
* Docker.
* Configuracion de produccion.
* Variables secretas.
* Logica de negocio.

No cambies ninguna funcionalidad existente.

El objetivo es que la aplicacion conserve exactamente el mismo comportamiento, pero tenga un frontend visualmente
renovado, coherente, premium y facil de utilizar.

Si detectas un problema funcional no relacionado con el rediseno:

1. No lo arregles dentro de esta tarea.
2. Documentalo al final.
3. Continua con el rediseno visual cuando sea posible.

---

# 2. ANALIZA LA APLICACION ANTES DE EDITAR

Antes de escribir codigo:

1. Localiza y lee:

   * `AGENTS.md`.
   * `README`.
   * Documentacion del frontend.
   * Guias de estilo existentes.
   * Configuracion de compilacion.
   * Sistema de rutas.
2. Identifica:

   * Tecnologia frontend.
   * Framework o sistema de plantillas.
   * Componentes reutilizables.
   * CSS global.
   * Variables CSS.
   * Sistema de temas.
   * Libreria de iconos.
   * Formularios.
   * Navegacion.
   * Modales.
   * Toasts.
   * Estados de carga y error.
   * Pruebas existentes.
3. Realiza un inventario completo de todas las rutas y pantallas.
4. Identifica que archivos son exclusivamente frontend.
5. Identifica que archivos contienen logica compartida con el backend y no deben tocarse.
6. Detecta componentes repetidos que deban unificarse visualmente.
7. Explica brevemente el plan de integracion antes de modificar archivos.

No reconstruyas la aplicacion desde cero.

No migres a otro framework.

No introduzcas React, Vue, Tailwind, Bootstrap, shadcn u otra tecnologia si la aplicacion no la utiliza actualmente.

Adapta el sistema visual a la arquitectura existente.

---

# 3. AZUL MARINO PRINCIPAL: DEBE SALIR DEL LOGO REAL

El azul marino principal del nuevo diseno debe ser exactamente el azul marino del fondo del logo real de la
aplicacion.

No utilices un azul aproximado si el archivo del logo esta disponible.

## Procedimiento obligatorio

1. Localiza todos los archivos del logo:

   * SVG.
   * PNG.
   * WebP.
   * Iconos de la PWA.
   * Favicon.
   * Assets alternativos.
2. Determina cual es el logo oficial utilizado por la aplicacion.
3. Inspecciona el fondo azul marino del logo.
4. Si es SVG:

   * Lee directamente el valor `fill`, `stroke`, gradiente o variable utilizada.
5. Si es una imagen raster:

   * Extrae el color predominante del fondo azul marino.
   * Evita pixeles de bordes suavizados, sombras o reflejos.
   * Obten un valor HEX representativo del area central uniforme.
6. Define ese color como token principal:

   * `--brand-navy`.
7. Utiliza exactamente ese token en:

   * Fondos de cristal azul marino.
   * Navegacion inferior.
   * Cabeceras azules.
   * Botones secundarios oscuros.
   * Pantalla de login.
   * Modales destacados.
   * Zonas donde aparezca el logo.
8. El fondo que rodea al logo debe utilizar el mismo `--brand-navy` cuando se quiera integrar visualmente.

## Objetivo visual

Cuando el logo aparezca encima de una superficie azul marino:

* No debe distinguirse un rectangulo de otro azul alrededor del logo.
* El fondo del propio logo debe fundirse visualmente con la superficie.
* No deben existir dos azules marinos ligeramente diferentes.
* El logo debe parecer integrado en la interfaz, no pegado encima.

Si el logo incluye transparencia, conserva la transparencia.

No edites ni recolorees el logo salvo que sea estrictamente necesario y se documente.

Si no puedes determinar el color exacto automaticamente:

1. No inventes un valor silenciosamente.
2. Documenta que archivos has inspeccionado.
3. Utiliza provisionalmente `#0B2341`.
4. Marca claramente que debe validarse contra el logo.

---

# 4. PALETA PRINCIPAL

La aplicacion debe ser mayoritariamente clara.

Distribucion visual aproximada:

* 65-75 %: fondos claros y superficies blancas.
* 15-25 %: azul marino del logo.
* 5-10 %: azul claro o cian.
* 3-6 %: naranja.
* Colores semanticos adicionales solo cuando sean necesarios.

Define un sistema de tokens semejante a este, adaptandolo al sistema actual:

```css
:root {
  color-scheme: light;

  /* Debe sustituirse por el color extraido del logo real */
  --brand-navy: #0b2341;
  --brand-navy-rgb: 11, 35, 65;

  --brand-navy-dark:
    color-mix(in srgb, var(--brand-navy) 88%, black);

  --brand-navy-light:
    color-mix(in srgb, var(--brand-navy) 82%, white);

  --brand-cyan: #19bff2;
  --brand-cyan-dark: #079ccf;
  --brand-cyan-light: #a9ebff;

  --brand-orange: #f4a62a;
  --brand-orange-dark: #cf7d08;
  --brand-orange-light: #fff1d6;

  --background-primary: #f4f7fb;
  --background-secondary: #edf3f8;
  --surface-primary: #ffffff;
  --surface-secondary: #f8fafc;

  --text-primary: #101828;
  --text-secondary: #667085;
  --text-tertiary: #98a2b3;
  --text-on-navy: #f7fbff;

  --border-default: #e4e7ec;
  --divider-default: #eaecf0;

  --success: #20b486;
  --success-surface: #eafaf4;

  --warning: var(--brand-orange);
  --warning-surface: var(--brand-orange-light);

  --error: #e5484d;
  --error-surface: #fff0f0;

  --glass-navy-background:
    rgba(var(--brand-navy-rgb), 0.84);

  --glass-navy-background-strong:
    rgba(var(--brand-navy-rgb), 0.92);

  --glass-navy-border:
    rgba(169, 235, 255, 0.68);

  --glass-navy-highlight:
    rgba(255, 255, 255, 0.34);

  --radius-small: 10px;
  --radius-medium: 16px;
  --radius-large: 22px;
  --radius-extra-large: 28px;
  --radius-pill: 999px;

  --shadow-card:
    0 5px 18px rgba(16, 24, 40, 0.07);

  --shadow-glass:
    0 14px 34px rgba(var(--brand-navy-rgb), 0.22),
    inset 0 1px 0 rgba(255, 255, 255, 0.34),
    inset 0 -1px 0 rgba(0, 0, 0, 0.14);

  --touch-target: 44px;
  --content-max-width: 520px;
}
```

Si `color-mix()` no encaja con la compatibilidad actual, calcula colores estaticos equivalentes.

Si el proyecto ya tiene una paleta corporativa con azul claro y naranja, utiliza sus valores reales en lugar de
duplicar colores parecidos.

---

# 5. DESCRIPCION RESUMIDA DE TINTED NAVY LIQUID GLASS

Tinted Navy Liquid Glass es una interfaz clara y minimalista que utiliza superficies de cristal liquido tenidas con
el azul marino corporativo.

Debe combinar:

* Fondo general claro.
* Tarjetas de datos blancas.
* Formularios solidos.
* Navegacion azul marino.
* Paneles destacados azul marino.
* Botones principales azul claro.
* Naranja para acciones o avisos concretos.
* Transparencia moderada.
* Desenfoque de fondo.
* Bordes azul claro refractivos.
* Reflejos blancos interiores.
* Sombras suaves.
* Jerarquia visual muy clara.

El azul marino debe dominar los elementos de identidad, pero no toda la pantalla.

Principio obligatorio:

> El contenido permanece solido y claro; la navegacion, la identidad y las acciones destacadas flotan en cristal azul
> marino.

---

# 6. USO DE LOS COLORES

## Azul marino del logo

Utilizalo para:

* Fondo integrado del logo.
* Barra de navegacion inferior.
* Panel principal de resumen.
* Cabeceras especiales.
* Contenedores de acciones importantes.
* Botones secundarios oscuros.
* Algunos modales.
* Barra contextual de revision.
* Elementos seleccionados.
* Login, de forma parcial y equilibrada.

## Azul claro

Utilizalo para:

* Botones principales.
* Accion "Crear factura".
* Estados activos.
* Foco.
* Bordes refractivos.
* Enlaces.
* Indicadores de progreso.
* Iconos seleccionados.
* Microdetalles de identidad.

## Naranja

Utilizalo de forma limitada para:

* Estados pendientes.
* Advertencias.
* Elementos que requieren atencion.
* Acciones secundarias concretas.
* Indicadores o pequenas zonas de identidad.

El naranja no debe competir con el boton principal azul claro.

No utilices naranja para errores. Los errores deben conservar rojo semantico.

---

# 7. COMPONENTE TINTED NAVY LIQUID GLASS

Crea un componente o clase reutilizable adaptada a la arquitectura actual.

Referencia CSS:

```css
.tinted-navy-glass {
  position: relative;
  isolation: isolate;
  overflow: hidden;

  color: var(--text-on-navy);

  background:
    linear-gradient(
      145deg,
      rgba(var(--brand-navy-rgb), 0.78) 0%,
      rgba(var(--brand-navy-rgb), 0.86) 52%,
      rgba(var(--brand-navy-rgb), 0.94) 100%
    );

  border: 1px solid var(--glass-navy-border);
  border-radius: var(--radius-large);

  -webkit-backdrop-filter: blur(18px) saturate(145%);
  backdrop-filter: blur(18px) saturate(145%);

  box-shadow: var(--shadow-glass);

  transition:
    transform 140ms cubic-bezier(0.2, 0.8, 0.2, 1),
    border-color 220ms ease,
    box-shadow 220ms ease;
}

.tinted-navy-glass::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;

  background:
    linear-gradient(
      130deg,
      rgba(255, 255, 255, 0.34) 0%,
      rgba(255, 255, 255, 0.1) 20%,
      transparent 48%
    );

  pointer-events: none;
}

.tinted-navy-glass::after {
  content: "";
  position: absolute;
  inset: 1px;
  z-index: -1;

  border-radius: calc(var(--radius-large) - 1px);

  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.34),
    inset 1px 0 0 rgba(169, 235, 255, 0.14),
    inset -1px 0 0 rgba(169, 235, 255, 0.08);

  pointer-events: none;
}

.tinted-navy-glass[data-interactive="true"]:active {
  transform: scale(0.985);
}

.tinted-navy-glass:focus-visible {
  outline: 3px solid rgba(25, 191, 242, 0.38);
  outline-offset: 3px;
}
```

Fallback obligatorio:

```css
@supports not (
  (backdrop-filter: blur(1px)) or
  (-webkit-backdrop-filter: blur(1px))
) {
  .tinted-navy-glass {
    background: var(--brand-navy);
  }
}
```

No utilices WebGL.

No utilices efectos liquidos que necesiten capturar la pantalla.

No anadas animaciones permanentes.

No anides varios cristales entre si.

---

# 8. DONDE APLICAR EL CRISTAL

Aplicalo de forma selectiva a:

* Navegacion inferior.
* Tarjeta principal del mes.
* Cabeceras flotantes.
* Controles circulares.
* Botones secundarios oscuros.
* Panel de confirmacion.
* Modales compactos.
* Menus contextuales.
* Barra de acciones durante la revision.
* Contenedor del logo cuando deba integrarse con el fondo.

No lo apliques a:

* Todos los campos del formulario.
* Todas las facturas.
* Tablas.
* Textos legales.
* Detalles fiscales completos.
* Grandes zonas desplazables.
* Listas extensas.
* Fondos completos de todas las pantallas.

---

# 9. REDISENO DEL LOGIN

La pantalla de login tambien debe redisenarse.

Debe incluir:

1. Logo perfectamente integrado con el azul marino real.
2. Fondo general claro.
3. Una zona superior o panel de marca azul marino.
4. Formulario sobre superficie blanca solida.
5. Boton principal azul claro.
6. Enlaces secundarios en azul marino o azul claro.
7. Naranja unicamente para aviso o elemento secundario.
8. Mensajes de error claramente visibles.
9. Contraste alto.
10. Diseno movil prioritario.

El fondo azul marino detras del logo debe usar exactamente `--brand-navy`.

No coloques el logo con su rectangulo azul sobre otro azul diferente.

No cambies:

* Logica de login.
* Endpoint.
* Validacion.
* Gestion de sesion.
* Recuperacion de contrasena.
* Redirecciones.
* Mensajes funcionales.

Ejemplo conceptual:

```html
<main class="auth-layout">
  <section class="auth-brand tinted-navy-glass">
    <img
      class="auth-logo"
      src="RUTA_REAL_DEL_LOGO"
      alt="Nombre real de la aplicacion"
    />

    <h1>Gestiona tus facturas facilmente</h1>
    <p>Todo lo necesario para crear, revisar y enviar facturas.</p>
  </section>

  <section class="auth-form-card">
    <!-- Conservar el formulario real y su logica -->
  </section>
</main>
```

No copies literalmente este HTML si la aplicacion utiliza componentes o plantillas distintas.

---

# 10. RESTO DE PANTALLAS

## Inicio

* Fondo claro.
* Resumen principal en Tinted Navy.
* Accion "Crear factura" en azul claro.
* Facturas recientes blancas.
* Estados pendientes en naranja.
* Navegacion inferior azul marino.

## Listado de facturas

* Fondo claro.
* Buscador blanco.
* Filtros activos con azul claro.
* Facturas sobre superficies blancas.
* Azul marino para cabecera o controles.
* Naranja para pendientes.
* Rojo para errores.
* Verde para pagadas o completadas.

## Creacion y edicion

* Formularios blancos.
* Etiquetas persistentes.
* Campos con foco azul claro.
* Barra de progreso azul claro.
* Barra inferior de acciones en azul marino.
* Una accion principal visible por paso.
* No utilizar cristal detras de los campos.

## Revision

* Datos fiscales sobre fondo blanco.
* Total claramente destacado.
* Barra de acciones Tinted Navy.
* Accion principal azul claro.
* Advertencias naranjas.
* Errores rojos.

## Confirmacion

* Panel Tinted Navy.
* Icono verde.
* Importe con alto contraste.
* Boton principal azul claro.
* Accion secundaria discreta.

## Perfil y configuracion

* Fondo claro.
* Secciones blancas.
* Encabezado azul marino moderado.
* Toggles y elementos activos en azul claro.
* Acciones de riesgo en rojo, nunca naranja.

## Estados vacios

* Mensaje breve.
* Ilustracion o icono sencillo.
* Una accion principal.
* Sin paneles decorativos innecesarios.

## Carga

* Skeletons solidos.
* No utilizar grandes bloques transparentes animados.
* Evitar movimientos que consuman bateria.

---

# 11. NAVEGACION INFERIOR

Debe conservar los destinos reales existentes.

No elimines una seccion funcional unicamente por simplificar visualmente.

Si actualmente existen tres destinos principales, prioriza:

* Inicio.
* Facturas.
* Perfil.

La navegacion debe:

* Usar el azul marino exacto del logo.
* Tener iconos y texto.
* Indicar la opcion activa mediante azul claro y cambio adicional de fondo o borde.
* Respetar `safe-area-inset-bottom`.
* Tener objetivos tactiles minimos de `44 x 44px`.
* No ocultar el contenido.
* No romperse al abrir el teclado.

---

# 12. COMPONENTES SOLIDOS

Utiliza superficies solidas para datos:

```css
.surface-card {
  color: var(--text-primary);
  background: var(--surface-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-medium);
  box-shadow: var(--shadow-card);
}
```

Utilizalas para:

* Facturas.
* Clientes.
* Formularios.
* Desgloses fiscales.
* Datos legales.
* Lineas de factura.
* Totales.
* Informacion detallada.

---

# 13. FORMULARIOS

No cambies:

* `name`.
* `id` necesarios para logica.
* Binding.
* Eventos.
* Validaciones.
* Formato enviado al backend.
* Campos obligatorios.
* Secuencia funcional.

Solo mejora:

* Distribucion.
* Espaciado.
* Etiquetas.
* Foco.
* Errores.
* Claridad.
* Tamano tactil.
* Organizacion visual.

Requisitos:

* Inputs de al menos `16px`.
* Etiquetas persistentes.
* Foco azul claro.
* Errores rojos asociados al campo.
* Ayuda textual cuando sea necesaria.
* Boton principal claramente separado.
* No depender unicamente de placeholders.
* No utilizar cristal en inputs.

---

# 14. RESPONSIVE Y EXPERIENCIA MOVIL

Disena primero para movil.

Prueba como minimo:

* `320px`.
* `360px`.
* `375px`.
* `390px`.
* `412px`.
* `430px`.
* `768px`.
* Escritorio.

Requisitos:

* Sin scroll horizontal.
* Sin textos cortados.
* Sin botones fuera de pantalla.
* Sin contenido oculto tras navegacion fija.
* Respeto de areas seguras.
* Formularios utilizables con teclado virtual.
* Objetivos tactiles minimos de `44px`.
* Importes con digitos tabulares.
* Nombres largos correctamente gestionados.
* Contraste correcto en exteriores.

---

# 15. ACCESIBILIDAD

Cumple WCAG 2.2 AA:

* Contraste normal minimo `4.5:1`.
* Contraste de texto grande minimo `3:1`.
* Foco visible.
* Navegacion por teclado.
* Etiquetas asociadas.
* `aria-invalid`.
* `aria-describedby`.
* `aria-current`.
* Botones semanticos.
* Enlaces semanticos.
* Iconos decorativos con `aria-hidden`.
* Botones de icono con nombre accesible.
* Zoom al 200 %.
* Estados no dependientes solo del color.
* Respeto de movimiento reducido.

Incluye:

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    scroll-behavior: auto !important;
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

@media (prefers-contrast: more) {
  .tinted-navy-glass {
    background: var(--brand-navy);
    border-color: #ffffff;
  }
}
```

---

# 16. RENDIMIENTO

* Prioriza CSS nativo.
* No utilices WebGL.
* No utilices canvas para simular cristal.
* No uses `html2canvas`.
* No apliques `backdrop-filter` a grandes superficies.
* Limita los elementos de cristal simultaneos.
* No anides cristal dentro de cristal.
* No animes filtros permanentemente.
* No anadas dependencias pesadas.
* No utilices versiones `@latest`.
* Manten desplazamiento fluido.
* Implementa fallback.
* No hagas que una funcionalidad dependa de un efecto visual.

---

# 17. DESACTIVACION GLOBAL

Permite desactivar el efecto sin romper el tema:

```css
[data-liquid-glass="off"] .tinted-navy-glass {
  background: var(--brand-navy);
  border-color: rgba(255, 255, 255, 0.18);

  -webkit-backdrop-filter: none;
  backdrop-filter: none;
}

[data-liquid-glass="off"] .tinted-navy-glass::before,
[data-liquid-glass="off"] .tinted-navy-glass::after {
  display: none;
}
```

---

# 18. PROCESO DE TRABAJO

Ejecuta en este orden:

1. Inspeccion del repositorio.
2. Inventario completo de pantallas.
3. Localizacion del logo.
4. Extraccion del azul marino exacto.
5. Definicion de tokens.
6. Mapeo del sistema visual.
7. Rediseno de componentes globales.
8. Rediseno del login.
9. Rediseno de todas las pantallas autenticadas.
10. Estados vacios, carga y error.
11. Responsive.
12. Accesibilidad.
13. Rendimiento.
14. Pruebas existentes.
15. Pruebas visuales.
16. Capturas.
17. Informe final.

No te detengas despues de cambiar unicamente Inicio. Recorre todas las rutas reales.

No realices refactorizaciones generales no relacionadas.

---

# 19. PRUEBAS OBLIGATORIAS

Comprueba:

* Login correcto.
* Login incorrecto.
* Recuperacion de contrasena.
* Navegacion.
* Creacion de factura.
* Edicion.
* Validacion.
* Revision.
* Confirmacion.
* Listados.
* Modales.
* Notificaciones.
* Perfil.
* Logout.
* Carga.
* Vacio.
* Error.
* Offline, si existe.
* Chrome Android.
* Safari iOS o WebKit.
* Firefox.
* Navegador sin `backdrop-filter`.
* Movimiento reducido.
* Contraste aumentado.
* Teclado.
* Zoom al 200 %.
* Pantallas moviles pequenas.
* Tableta.
* Escritorio.

Ejecuta las pruebas existentes.

No elimines ni debilites pruebas para conseguir que pasen.

---

# 20. CRITERIOS DE ACEPTACION

El trabajo estara terminado cuando:

1. Todas las pantallas tengan el nuevo diseno.
2. Login este incluido.
3. La aplicacion siga funcionando igual.
4. No se haya modificado el backend.
5. El azul marino coincida con el fondo real del logo.
6. El logo se integre sin un rectangulo de otro azul.
7. La aplicacion sea mayoritariamente clara.
8. El azul marino se reserve para identidad y navegacion.
9. El azul claro identifique acciones principales.
10. El naranja se use con moderacion.
11. Los formularios sean solidos y legibles.
12. El cristal se utilice selectivamente.
13. Exista fallback sin `backdrop-filter`.
14. Se cumpla WCAG AA.
15. No exista scroll horizontal.
16. La navegacion sea comoda con una mano.
17. Las pruebas existentes sigan pasando.
18. Se hayan generado capturas de todas las pantallas principales.
19. Se documente el HEX final extraido del logo.
20. Se entregue una lista exacta de archivos modificados.

---

# 21. ENTREGA FINAL

Entrega:

1. Resumen del rediseno.
2. Azul marino extraido del logo:

   * Archivo de origen.
   * Valor HEX.
   * Valor RGB.
3. Paleta definitiva.
4. Inventario de rutas revisadas.
5. Pantallas modificadas.
6. Componentes modificados.
7. Archivos creados.
8. Archivos modificados.
9. Confirmacion explicita de que no se modifico el backend.
10. Pruebas ejecutadas.
11. Resultados.
12. Capturas de:

    * Login.
    * Inicio.
    * Facturas.
    * Creacion.
    * Revision.
    * Confirmacion.
    * Perfil.
    * Estados de error y vacio.
13. Comportamiento sin `backdrop-filter`.
14. Limitaciones reales.
15. Instrucciones para desactivar o revertir exclusivamente el nuevo tema.

No afirmes que una pantalla esta terminada si no la has abierto y comprobado.

Comienza inspeccionando el repositorio y localizando el logo oficial. Antes de aplicar cambios masivos, indica el
valor exacto del azul marino detectado y el listado completo de pantallas que vas a redisenar.

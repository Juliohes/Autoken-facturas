# Spec: R-052 Flujo de revisión, borrado, duplicados y latencia de captura

> Spec-Driven Domain. Esta spec es la **fuente única** que alimenta los tests (TDD) y las 3 auditorías.
> Si algo no está aquí, no se implementa. Aprobada por Julio antes de escribir tests.

- **ID / tarea:** R-052
- **Contexto (módulo):** `frontend` (`capture`, `confirmation`, `inbox`) + `invoice_intake` + `invoicing`
- **ADR relacionados:** ADR-0001 (RLS y aislamiento por tenant), ADR-0015 (object storage privado), ADR-0006 (inmutabilidad posterior a confirmación)
- **Estado:** aprobada por Julio (2026-08-27)

## 1. Problema y valor de dominio

El usuario necesita revisar facturas pendientes sin que la aplicación le cambie de factura por sorpresa.
También necesita descartar una factura todavía no confirmada para volver a fotografiarla, y debe quedar
protegido frente a subir o confirmar la misma factura dos veces.

La captura debe ofrecer una respuesta visible y medible en el ordenador local: se registrará cuánto tarda
cada fase entre pulsar **Tomar foto** y mostrar **Usar foto**, para eliminar esperas que no aportan valor.

## 2. Lenguaje ubicuo

- **Factura pendiente:** documento que todavía no se ha confirmado y guardado definitivamente, incluyendo
  `pending_ocr`, `processing`, `ocr_done` y `needs_review`.
- **Factura confirmada:** documento cuyo `POST confirm` terminó correctamente y tiene registro definitivo.
- **Duplicado exacto:** fichero cuyo contenido produce el mismo SHA-256 que otro fichero visible del mismo
  contexto de empresa y usuario, según la política actual de intake.
- **Duplicado por datos:** factura que coincide con otra factura del mismo contexto en los campos fiscales
  requeridos por esta spec.
- **Sospecha de duplicado:** coincidencia de número de factura y ambos CIF cuando esos tres valores están
  disponibles y coinciden, aunque no exista todavía coincidencia del importe.
- **Duplicado confirmado por datos:** coincidencia de número de factura, CIF propio, CIF de contraparte e
  importe cuando los cuatro valores están disponibles y coinciden.
- **Ambos CIF:** CIF de la empresa propia y CIF de la contraparte.
- **Vista previa:** pantalla posterior a la captura donde el usuario decide entre **Repetir** y **Usar foto**.
- **Factura siguiente:** primera factura revisable (`ocr_done` o `needs_review`) que queda en la bandeja tras
  confirmar la factura actual.

## 3. Comportamientos (criterios de aceptación)

### C1 — Confirmar no cambia de factura automáticamente
- **Given** el usuario confirma y guarda una factura y queda al menos otra factura revisable.
- **When** termina correctamente la confirmación.
- **Then** la aplicación no navega automáticamente a la otra factura y muestra un diálogo preguntando si
  quiere revisarla.

### C2 — Elegir revisar la siguiente factura
- **Given** está visible el diálogo posterior a una confirmación y existe una factura siguiente.
- **When** el usuario elige **Sí, revisar**.
- **Then** se abre la primera factura revisable de la bandeja, respetando el orden actual de la bandeja.

### C3 — Elegir volver a la bandeja
- **Given** está visible el diálogo posterior a una confirmación.
- **When** el usuario elige **No, volver a mis facturas**.
- **Then** la aplicación navega a `Mis facturas` y no abre ninguna otra factura.

### C4 — No hay diálogo si no quedan facturas revisables
- **Given** el usuario confirma y guarda una factura y no queda ninguna factura revisable.
- **When** termina correctamente la confirmación.
- **Then** la aplicación navega a `Mis facturas` sin mostrar un diálogo de siguiente factura.

### C5 — El usuario puede borrar una factura pendiente
- **Given** el usuario es propietario de una factura pendiente que aún no está confirmada.
- **When** pulsa **Eliminar**, acepta la confirmación y la operación termina correctamente.
- **Then** la factura, su borrador, sus páginas y sus objetos asociados dejan de aparecer como pendientes,
  el usuario vuelve a `Mis facturas` y ve el mensaje: `La factura no se ha confirmado ni guardado.`

### C6 — El borrado exige confirmación y no borra al cancelar
- **Given** el usuario está viendo una factura pendiente.
- **When** pulsa **Eliminar** y cancela el diálogo.
- **Then** la factura permanece intacta y no se solicita ningún borrado al servidor.

### C7 — Una factura confirmada no se puede borrar
- **Given** una factura ya fue confirmada y guardada.
- **When** el usuario intenta eliminarla mediante cualquier camino de la aplicación.
- **Then** el servidor rechaza la operación, la factura permanece disponible y la interfaz muestra que las
  facturas confirmadas no se pueden eliminar.

### C8 — Un duplicado exacto no crea una segunda factura
- **Given** el usuario intenta subir un fichero con el mismo contenido que un fichero visible existente.
- **When** termina la subida.
- **Then** no se crea un nuevo documento ni se consume una posición de captura continua, se muestra un aviso
  de duplicado y se ofrecen **Revisar la factura original** y **Repetir la foto**.

### C9 — Una coincidencia por número y CIF se marca como sospecha
- **Given** una factura pendiente o confirmada del mismo contexto tiene el mismo número de factura, CIF propio
  y CIF de contraparte, y esos tres valores están disponibles.
- **When** termina el OCR de una nueva factura con esa misma combinación.
- **Then** la nueva factura se marca como sospecha de duplicado, se muestra el aviso identificando la factura
  existente cuando sea posible y no se permite continuar con la nueva sin elegir revisar la existente o
  eliminar la nueva factura pendiente.

### C10 — La coincidencia completa se marca como duplicado confirmado
- **Given** una factura pendiente o confirmada del mismo contexto tiene el mismo número, ambos CIF e importe,
  y los cuatro valores están disponibles.
- **When** termina el OCR o se intenta confirmar la nueva factura.
- **Then** la nueva factura se marca como duplicado confirmado, se muestra un aviso claro y no se permite
  confirmar ni guardar la nueva factura.

### C11 — El servidor revalida el duplicado al guardar
- **Given** dos usuarios o dos solicitudes intentan confirmar facturas con la misma identidad fiscal.
- **When** la segunda confirmación llega al servidor después de que la primera haya sido guardada.
- **Then** el servidor rechaza la segunda operación como duplicada, conserva una sola factura confirmada y la
  interfaz ofrece revisar la existente o eliminar la nueva si todavía está pendiente.

### C12 — La medición de captura identifica la espera real
- **Given** el usuario utiliza la captura en un ordenador local.
- **When** pulsa **Tomar foto** hasta que aparece la vista previa con **Usar foto**.
- **Then** quedan registradas, sin imagen ni datos fiscales, las duraciones de captura del frame, análisis,
  recorte/normalización y creación de la vista previa, además del tiempo total.

### C13 — La medición no bloquea la captura
- **Given** la captura o el análisis de calidad tarda más de lo esperado.
- **When** se prepara la vista previa.
- **Then** la telemetría no impide mostrar la vista previa ni cambia la decisión del usuario; cualquier
  optimización posterior debe conservar la calidad y el flujo explícito **Repetir / Usar foto**.

### C14 — El análisis de calidad no bloquea la captura
- **Given** se ha capturado un frame válido pero el análisis OpenCV no está disponible o falla.
- **When** se prepara la vista previa.
- **Then** se conserva la imagen completa, se muestra **Usar foto** y la persona puede continuar sin
  recibir un error engañoso de preparación; la información opcional de nitidez queda ausente.

## 4. Invariantes y reglas de negocio

- El backend es la autoridad final: la interfaz nunca sustituye las guardas de borrado o duplicado.
- Una factura confirmada es inmutable respecto al borrado.
- El borrado solo afecta a facturas pendientes autorizadas del propio usuario; un usuario nunca puede borrar
  datos de otro usuario, empresa o tenant.
- Toda detección de duplicado respeta el aislamiento por tenant y empresa; no revela datos de otro contexto.
- El duplicado exacto se compara con el hash privado ya calculado durante intake.
- Los campos ausentes o no legibles no se inventan ni cuentan como coincidencia.
- Una sospecha por número y ambos CIF bloquea la continuación de la nueva factura hasta que el usuario la
  revise o la elimine.
- Una coincidencia completa por número, ambos CIF e importe bloquea siempre la confirmación de la nueva
  factura.
- El diálogo posterior a confirmación aparece siempre que exista una factura revisable, tanto en captura
  individual como en captura múltiple o continua.
- La telemetría de captura no contiene imagen, OCR, CIF, número de factura ni importes.

## 5. Casos límite y errores

- Si el borrado falla, la factura permanece visible y se muestra un error reintentable; no se informa de éxito
  parcial como si todo hubiera desaparecido.
- Si falla la limpieza del object storage después de borrar la fila autorizada, la operación se audita y se
  reintenta mediante el mecanismo de limpieza existente, sin volver a mostrar la factura como pendiente.
- Si la factura está siendo procesada mientras se solicita el borrado, el servidor debe impedir que el worker
  la vuelva a publicar como revisable.
- Si una confirmación llega mientras se está borrando, solo una operación puede ganar; nunca se permite borrar
  una factura ya confirmada.
- Si no existe la factura original del duplicado exacto, se muestra un error recuperable y se permite repetir
  la captura.
- Si faltan uno o más campos fiscales, no se declara duplicado por datos; el documento sigue sujeto a las
  guardas normales de revisión.
- Si no se puede consultar la bandeja tras confirmar, no se bloquea la confirmación; se vuelve a `Mis facturas`
  y no se navega a una factura elegida con datos obsoletos.
- Si el navegador no admite alguna marca de rendimiento, la captura continúa y se conserva como mínimo la
  medición disponible del tiempo total.

## 6. Fuera de alcance (no-objetivos)

- No se cambia la política de duplicados entre tenants ni se permite consultar duplicados de otra empresa.
- No se borran facturas confirmadas mediante una acción de usuario, soporte o pantalla administrativa dentro
  de esta tarea.
- No se añade deduplicación difusa por nombre, fecha, redondeos o similitud de imagen; solo se implementan el
  hash exacto y las combinaciones fiscales descritas.
- No se usa OCR adicional solo para buscar duplicados.
- No se define todavía un SLA fijo en milisegundos para la vista previa; primero se mide el ordenador local.
- No se modifica la calidad visual, el máximo de páginas ni los modos de captura existentes salvo lo necesario
  para eliminar esperas demostradas.
- No se despliega a producción ni se usan datos fiscales reales para validar la deduplicación.

## 7. Notas de verificación (cómo se prueba de extremo a extremo)

- Frontend: tests de comportamiento para el diálogo posterior a confirmación, las acciones de borrado, los
  avisos de duplicado y las marcas de rendimiento.
- Backend: tests HTTP con RLS para borrado propio, rechazo de confirmadas, aislamiento entre tenants y carrera
  de confirmación duplicada.
- Integración: una captura exacta repetida, una factura con misma combinación número+CIF y una factura con los
  cuatro campos coincidentes, usando fixtures sintéticos.
- Staging: comprobar primero las respuestas y estados con un tenant aislado y documentos de prueba; no usar
  facturas reales del tenant de Setex.
- Rendimiento local: revisar las medidas de cada fase en DevTools y comparar antes/después sin contar el tiempo
  de espera del OCR remoto.

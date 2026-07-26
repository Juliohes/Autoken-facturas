# Guía en cristiano — Autoken Facturas

> Este archivo explica el proyecto **para quien no sabe de software**: qué hace la aplicación, cómo está
> construida por dentro (en plano, sin tecnicismos innecesarios) y qué se ha ido añadiendo, iteración a
> iteración. Se actualiza **cada vez que se cierra una tarea**. La fuente técnica de verdad sigue siendo
> `PLAN_MAESTRO_AUTOKEN_FACTURAS_V2_v1.2.md` y el `CLAUDE.md`; este archivo es su traducción a lenguaje
> llano, para que Julio pueda entender y seguir el proyecto sin necesitar saber programar.

---

## 1. ¿Qué es esta aplicación?

Autoken Facturas es la **versión 2** de Setex, un programa donde las asesorías (gestorías/asesorías
fiscales) y las empresas que llevan reciben y suben las facturas de sus proveedores (y las que emiten a sus
clientes), y un **lector automático con inteligencia artificial (IA)** extrae los datos importantes de cada
factura (fecha, importes, quién la emite, IVA...) para que la persona solo tenga que **revisar y confirmar**,
en vez de teclearlo todo a mano.

La diferencia clave de la v2 frente a la v1 es que **una sola instalación sirve a muchas asesorías a la
vez** (se llama "multi-tenant", lo explico abajo), cada una viendo solo sus propios datos, como si cada
una tuviera su propia app aunque compartan el mismo edificio por dentro.

## 2. ¿Cómo está construida por dentro? (mapa sencillo, sin tecnicismos)

Piensa en la aplicación como un **edificio de oficinas con varias plantas**, donde cada planta hace un
trabajo concreto y solo habla con las plantas de al lado que necesita:

- **Planta de identidad y acceso** (`identity`, `tenancy`): comprueba quién eres, con qué contraseña, y a
  qué asesoría perteneces. Es el guardia de seguridad de la entrada.
- **Planta de empresas** (`companies`): la lista de empresas-cliente de cada asesoría (a quién le llevan la
  contabilidad).
- **Planta de recepción de facturas** (`invoice_intake`): por aquí entra la foto o el PDF de cada factura.
  Comprueba que el fichero es válido, que no está infectado con virus, y lo guarda en un almacén seguro.
- **Planta del lector automático** (`ocr`): coge la foto guardada, se la pasa a una IA que "lee" la factura
  y extrae los datos, y avisa si algo no se ha leído bien (nunca se inventa un dato: si no se ve claro, se
  deja en blanco con un aviso, nunca un valor inventado).
- **Planta de verificación del proveedor** (`counterparty`): comprueba que el CIF (identificador fiscal) de
  quien emite la factura existe de verdad y coincide con su nombre oficial, contra fuentes públicas.
- **Planta de confirmación y archivo** (`invoicing`): aquí la persona revisa lo que leyó la IA, corrige si
  hace falta, y al confirmar, la factura queda guardada de forma definitiva y consultable en el historial.

**La pared entre asesorías** (lo que en la jerga técnica se llama "RLS" o aislamiento multi-tenant): cada
fila de datos en la base de datos lleva "pegada" la etiqueta de qué asesoría es suya, y el propio motor de
la base de datos (no el código de la aplicación) se niega a devolver ni una fila que no sea de quien
pregunta. Es como si cada asesoría tuviera su propio armario con llave dentro del mismo edificio: aunque
compartan pasillo, nadie puede abrir el armario de al lado. Esto se comprueba con una batería de tests
automáticos ("suite anti-cruce") que se ejecuta en cada cambio de código, para garantizar que nunca se
rompe esa pared.

## 3. Diccionario de términos (para no perderte)

| Término | Qué significa en cristiano |
|---|---|
| **Endpoint** | Una "puerta" concreta de la aplicación a la que el navegador o el móvil llaman para pedir o mandar un dato (ej. "dame el historial de facturas"). |
| **Backend / Frontend** | El backend es el motor que vive en el servidor (la "cocina"); el frontend es lo que ve y toca el usuario en el navegador (el "salón"). |
| **Base de datos / migración** | La base de datos es donde se guarda todo de forma permanente (como un archivador gigante). Una "migración" es un cambio ordenado y con fecha en la estructura de ese archivador (p. ej. "añadir una carpeta nueva"). |
| **RLS (seguridad por fila)** | La "pared" entre asesorías explicada arriba: la propia base de datos filtra qué puede ver cada quien. |
| **Test / suite de tests** | Un programa que comprueba automáticamente que una funcionalidad hace lo que debe. Una "suite" es un conjunto de esos programas. Si algo se rompe sin querer, los tests lo detectan antes de que llegue a producción. |
| **CI (integración continua)** | Un robot que, cada vez que se propone un cambio de código, ejecuta automáticamente todos los tests, revisa el estilo y construye la aplicación, antes de dejar que el cambio se junte con el resto. |
| **Rama / PR / merge** | Una "rama" es una copia de trabajo aislada donde se hace un cambio sin tocar la versión oficial todavía. Un "PR" (pull request) es la propuesta de traer ese cambio a la versión oficial; "mergear" es aceptarlo e incorporarlo, una vez todo está en verde. |
| **Worker** | Un proceso que trabaja "en segundo plano", sin que el usuario tenga que esperar mirando la pantalla (p. ej. el que llama a la IA para leer la factura). |
| **URL firmada** | Un enlace de descarga temporal y con fecha de caducidad (minutos), que solo sirve para descargar un fichero concreto y deja de funcionar pasado ese tiempo. Es como una entrada de cine de un solo uso. |
| **Auditoría en 3 lentes** | Antes de dar un cambio de código por bueno, tres revisores independientes (con "ojos frescos", sin haber visto cómo se construyó) lo repasan cada uno buscando un tipo de problema distinto: uno si el diseño está bien organizado, otro si respeta la arquitectura del proyecto, otro si hay agujeros de seguridad. |
| **Spec (especificación)** | Un documento que describe QUÉ debe pasar (el comportamiento esperado) antes de escribir una sola línea de código, y que Julio aprueba antes de empezar. |

## 4. Registro de lo construido, iteración a iteración

> Cada entrada resume una tarea ya cerrada: qué se construyó y para qué sirve, en lenguaje llano.

### Fase 0 — Cimientos del edificio (completada, junio 2026)
Antes de construir nada visible, se preparó el terreno: el repositorio de código en GitHub, los dos
servidores donde vive la aplicación (uno para desarrollo, otro que hospedaba la v1 antigua), el esqueleto
del backend y del frontend arrancando, y el robot de comprobaciones automáticas (CI) funcionando desde el
primer día.

### Fase 1 — Elegir qué "lector de facturas" (IA) usar (completada, junio-julio 2026)
Se probaron varios "lectores" de IA distintos (Azure, Gemini, GPT, Mistral, Claude...) contra facturas
reales, midiendo quién acertaba más datos y a qué coste. Ganó **Gemini 3 Flash**: es el motor que hoy lee
las facturas de verdad. También se construyó, para cualquier dato de identificación (CIF, IBAN...), una capa
de verificación matemática que comprueba que el número "cuadra" antes de darlo por bueno.

### Sprint 1 — Quién entra y cómo se organizan las asesorías (completado, julio 2026)
Se construyó toda la "planta de identidad": inicio de sesión seguro (con doble verificación para los
administradores), registro de nuevas asesorías con aprobación manual, gestión de las empresas-cliente de
cada asesoría (incluyendo importar el Excel con las 51 empresas de Setex), y el reparto de permisos según
el rol de cada persona (empleado / administrador de asesoría / administrador de la plataforma). Se cerró con
la primera batería de tests "anti-cruce": la prueba automática de que ninguna asesoría puede ver ni tocar
los datos de otra.

### Sprint 2 — El corazón: subir, leer y confirmar facturas (julio 2026)

- **S2.1 — Subida segura de facturas**: se abrió la "puerta de recepción". Cada fichero se guarda en un
  almacén separado por asesoría, pasa un antivirus, se comprueba que es realmente una imagen o PDF (no un
  fichero disfrazado), y se detecta si ya se había subido antes (para no duplicar).
- **S2.3 — El lector automático (worker OCR)**: cada factura subida se encola y un proceso en segundo plano
  la lee con la IA (Gemini 3 Flash), guarda lo que ha entendido y marca con una luz (verde/amarilla/roja) la
  confianza de cada dato. Si algo no se lee bien, queda en blanco con aviso — nunca se inventa un valor.
- **S2.4 — Pantalla de confirmación**: la persona ve lo que leyó la IA (con los tres datos más importantes
  siempre a la vista: total, quién la emite, y fecha) y confirma o corrige antes de guardar. Bajo el botón
  de confirmar hay siempre un aviso: la responsabilidad de lo confirmado es de quien lo confirma.
- **S2.8 — Verificación del proveedor (CIF de contraparte)**: antes de dejar confirmar, el sistema comprueba
  que el CIF de quien emite la factura existe de verdad (primero contra los proveedores ya conocidos de esa
  asesoría, luego contra registros públicos si hace falta), y avisa si el nombre no coincide con el oficial.
- **S2.5 — Guardado definitivo**: al confirmar, la factura queda archivada de verdad (con sus tramos de IVA
  y un registro de qué cambió el humano respecto a lo que leyó la IA, para poder mejorar el lector con el
  tiempo).
- **S2.6 — Historial de facturas** (21/07/2026): pantalla que enseña las facturas confirmadas de la **última
  semana**, la más reciente arriba, para que el empleado compruebe rápido que lo que ha subido está
  registrado. Nunca mezcla facturas de otra empresa ni las de prueba de un administrador.
- **S2.7 — Descarga segura de la imagen de la factura** (21/07/2026): hasta ahora nadie podía "ver" la foto
  de una factura ya subida desde la aplicación (solo la leía el lector de IA por dentro). Se abrió una
  ventanilla de descarga que da un enlace temporal (5 minutos) y personal — nadie puede adivinar ni reusar
  el enlace de otra asesoría — y se comprobó con un test real contra el almacén que, sin ese enlace firmado,
  no hay forma de leer el fichero de nadie.

**Con S2.7 el Sprint 2 queda completo**, salvo la captura guiada en el móvil (S2.2), que necesita probarse
en un teléfono real y queda pendiente hasta disponer de uno.

### Sprint 3 — El panel de la asesoría (en marcha, julio 2026)

- **S3.1 — Panel de facturas** (22/07/2026): la pantalla donde el administrador de la asesoría ve **todas**
  las facturas confirmadas de **todas** sus empresas-cliente (no solo la última semana de un empleado, eso
  es S2.6), con buscador y filtros (por fechas, por proveedor/CIF, por quién la confirmó, por si el
  proveedor quedó verificado, por empresa), y un botón "Ver" para abrir la foto original de cualquier
  factura (reutiliza el enlace temporal de S2.7). Es exclusivo del administrador; el empleado sigue con su
  historial de 7 días. Como puede haber muchísimas facturas, la lista se trae "por tandas" (botón "Cargar
  más") en vez de todas de golpe.
- **S3.2 — Descargar Excel** (22/07/2026): el botón "Descargar Excel" del panel, con los mismos filtros que
  se tengan puestos en pantalla (proveedor, fechas...), genera un `.xlsx` con TODAS las facturas que casan
  ese filtro (no solo la tanda visible) para trabajar fuera de la aplicación, igual que en la v1. La
  auditoría encontró y corrigió un riesgo real de seguridad: el nombre del proveedor de una factura lo lee
  la IA de un documento de un tercero, así que en teoría alguien podría intentar colar ahí algo con pinta
  de fórmula de Excel (`=...`) para que se ejecutara sola al abrir el fichero descargado; ahora ese texto
  siempre se guarda como texto plano, nunca como fórmula.
- **Ajuste menor** (22/07/2026, sesión paralela de Julio ya aterrizada): el % de IVA de un tramo se veía a
  veces como "21,0%" en vez de "21%"; corregido para mostrar siempre el número limpio sin decimales de
  sobra cuando no aportan nada.
- **S3.3 — Corregir una factura ya confirmada** (23/07/2026): a veces una factura confirmada tiene un dato
  mal leído que nadie notó hasta después (un importe, la fecha, el CIF del proveedor). El administrador
  puede corregirlo, y **queda constancia de quién cambió qué y cuál era el valor anterior** (no se puede
  "editar en silencio"). Si se cambia el CIF del proveedor, el sistema lo vuelve a verificar como si fuera
  nuevo. La auditoría encontró un fallo real: si alguien cambiaba SOLO el CIF sin actualizar también el
  nombre del proveedor, el sistema daba por bueno el CIF nuevo dejando el nombre antiguo sin comprobar
  contra él — ahora eso se bloquea y pide los dos datos juntos. Solo el administrador puede editar
  facturas; no hay pantalla nueva todavía (eso vendrá si hace falta), esta tarea era la capacidad de
  corregir con seguridad, no la pantalla para hacerlo cómodo.
- **S3.4 — Gestión de empresas y usuarios** (23/07/2026): la pantalla "Empresas" del administrador: una
  fila por empresa-cliente con su nombre, CIF, estado, notas, cuántos usuarios activos tiene, cuántas
  facturas reales le han confirmado y cuándo fue la última (más su fecha de alta como cliente) — datos que
  antes estaban repartidos y sin un sitio único donde verlos juntos. Desde ahí se da de alta una empresa
  nueva, se edita (incluidas las notas, que se guardaban desde hacía tiempo pero no se podían volver a leer
  en pantalla), se borra (bloqueado si tiene usuarios, para no perder historial), se enlaza a "ver sus
  facturas" en el panel de S3.1, y se aprueban o rechazan los registros de usuarios pendientes (la solicitud
  de alta que manda alguien nuevo, ya existía por detrás desde el Sprint 1 pero sin pantalla que la
  mostrara). La auditoría en tres capas encontró y corrigió un detalle de rendimiento: la primera versión de
  la consulta juntaba usuarios y facturas de la misma empresa en un único cruce, lo que multiplicaba filas
  de más por debajo antes de contarlas bien (el resultado final salía correcto, pero por un camino más
  costoso de lo necesario); se separó en dos cuentas independientes antes de unirlas a la empresa, un cruce
  más simple y que envejece mejor según crezca el histórico de facturas.
- **S3.5 — Facturas de prueba** (23/07/2026, cierra Sprint 3): un administrador ya podía decirle al
  sistema "esta factura es solo una prueba" al confirmarla, pero solo por detrás — la pantalla no tenía
  casilla para marcarlo, y esas pruebas se quedaban acumuladas para siempre sin forma de limpiarlas. Ahora
  la pantalla de confirmación muestra una casilla "Factura de prueba" (solo la ve un administrador, nunca
  un empleado) y hay un botón "Purgar facturas de prueba" que borra de golpe todas las de la asesoría —
  la factura, sus datos asociados y la foto original — sin poder tocar nunca una factura real (esa
  condición está fija por dentro del programa, no depende de lo que mande la pantalla). Para saber quién
  es administrador, la aplicación tuvo que empezar a preguntarle al servidor "¿quién eres?" por primera
  vez desde una pantalla (antes ninguna pantalla lo hacía). La auditoría encontró un detalle de eficiencia
  (borrar muchas fotos de golpe iba a mantener la operación "a medio hacer" más tiempo del necesario) y se
  corrigió: ahora los datos se borran primero de forma segura, y las fotos se limpian justo después,
  sin alargar la operación principal.

### Sprint 4 — El panel de la plataforma (arrancado, julio 2026)

- **S4.1 — Alta de tenant en minutos** (24/07/2026): hasta ahora, dar de alta una asesoría nueva en el
  sistema exigía meter la mano directamente en la base de datos. Julio/Alberto ya tienen una pantalla
  ("Plataforma — Asesorías") con un formulario (nombre, subdominio, logo, 2 colores) que crea la
  asesoría al momento — su subdominio (`nueva-asesoria.autoken.es`) queda listo para usarse sin tocar
  código ni reiniciar nada — y un listado de las que ya existen. Por dentro fue más delicado de lo que
  parece: la tabla de asesorías tiene una protección especial (cada una solo puede ver sus propios
  datos, ni siquiera la aplicación puede "ver todas a la vez" por defecto), así que hizo falta crear un
  mecanismo acotado, del mismo tipo que ya se usaba para el login de plataforma, que deja hacer
  exactamente dos cosas — crear una asesoría, listarlas todas — sin abrir ninguna otra puerta. La
  auditoría encontró y corrigió dos fallos reales antes de cerrar la tarea: un subdominio demasiado
  largo rompía con un error feo en vez de avisar con claridad, y se podía crear una asesoría sin nombre.
- **S4.2 — Theming runtime** (24/07/2026): cada asesoría ya podía guardar su logo y sus colores al
  darse de alta (S4.1), pero esos datos no se usaban para nada. Ahora, al arrancar, la aplicación
  pregunta "¿de qué asesoría es este subdominio y cómo se ve?" y aplica esos colores y ese logo — sin
  que la asesoría original (Setex) note ningún cambio, porque para ella todo sigue exactamente igual
  que hoy (sin logo ni colores propios, cae a los de siempre). Fue una tarea más sencilla de lo
  esperado por dentro: a diferencia del alta de asesorías (S4.1), leer el logo/colores no necesitó
  ningún permiso nuevo en la base de datos. La auditoría encontró y corrigió tres detalles: un trozo
  de código que ya existía en otro sitio del proyecto se estaba reescribiendo en vez de reutilizarse;
  un test que comprobaba un caso que en la práctica nunca puede pasar (se corrigió para probar el
  caso real); y se reforzó la prueba de que el logo/color de una asesoría nunca se cuela al pedir el
  de otra, probando directamente el candado de la base de datos, no solo el resultado final.
- **S4.3 — Manifest PWA dinámico** (24/07/2026): cuando alguien le da a "Instalar app" desde el móvil,
  hasta ahora siempre se instalaba "Autoken Facturas" con el icono genérico, sin importar de qué
  asesoría fuera. Ahora se instala con el nombre y el icono de la asesoría, tomados del logo y el
  nombre que ya se configuraron en S4.1. También se añadió el icono pequeño de la pestaña del
  navegador (favicon) por asesoría. La auditoría encontró y corrigió dos fallos reales antes de
  cerrar la tarea: uno impedía que el icono de instalación se viera bien en las asesorías SIN logo
  propio (un problema técnico de cómo el navegador entiende una dirección relativa, ya arreglado); y
  otro hacía que, si una asesoría configuraba SOLO el icono de la pestaña (sin tocar nombre ni
  colores), ese icono a veces no llegara a aparecer — también corregido y con una prueba nueva que
  vigila que no vuelva a pasar.

- **S4.4 — Modo demo** (24/07/2026): antes, dar de alta una asesoría para enseñarla en una reunión
  comercial y dar de alta un cliente real era exactamente lo mismo, sin distinción, y no había forma
  de deshacer una demo ni "graduarla" a cliente real sin borrar todo y volver a empezar. Ahora el
  alta tiene una casilla "Es demo"; una asesoría demo funciona exactamente igual que cualquier otra
  (login, facturas, logo/colores propios) pero gana dos botones nuevos en el panel de plataforma:
  "Convertir a producción" (cuando el prospecto firma, sin perder nada de lo ya configurado) y
  "Purgar" (la borra por completo — base de datos y ficheros — si no prospera). El botón de purgar
  solo puede actuar sobre asesorías demo: esa condición está fijada dentro de la propia base de
  datos, no en un interruptor que se pudiera manipular desde fuera, así que es estructuralmente
  imposible borrar por accidente una asesoría real por esta vía. La auditoría (con tres revisores en
  paralelo, cada uno mirando una cosa distinta) encontró un fallo real antes de cerrar la tarea: si
  dos peticiones de purgar/convertir la misma asesoría demo llegaban casi a la vez, la segunda podía
  acabar en un error feo en vez de una respuesta clara — se corrigió haciendo que la comprobación y
  el borrado ocurran como una sola operación indivisible dentro de la base de datos, sin ese hueco
  en medio. También se reforzaron las pruebas: que purgar una asesoría nunca toca a otra que
  coexista, que la caché compartida de CIFs (que no pertenece a ninguna asesoría) no se ve afectada,
  y los casos de error visibles en pantalla.

- **S4.5 — Métricas y consumo** (24/07/2026): el panel de plataforma ya deja crear asesorías y
  gestionar su modo demo, pero Julio no tenía forma de saber, sin entrar a mano en la base de
  datos, cuánto está usando de verdad cada una: cuántas empresas ha dado de alta, cuántos usuarios
  tiene activos, cuántas facturas mete al mes, cuántas veces ha usado el lector automático (OCR), y
  cuándo fue la última vez que hizo algo. Ahora el panel muestra una segunda tabla, "Métricas y
  consumo", con esos números por asesoría. Un matiz importante: el plan pedía enseñar el "coste de
  OCR acumulado" (cuánto ha costado en dinero), pero hoy la aplicación no guarda ese dato en ningún
  sitio (los proveedores de IA no siempre devuelven el precio exacto, y aún no existe una tabla de
  precios por modelo) — así que, en vez de inventar una cifra de dinero que no sería real, se
  muestra el número de facturas procesadas por el lector automático, dejando claro con el nombre de
  la columna que NO es una cantidad de euros. La auditoría (tres revisores en paralelo) no encontró
  ningún problema de diseño ni de seguridad; sí sugirió reforzar varias pruebas (que "empresas" y
  "facturas procesadas" cuenten de verdad TODOS los casos, no solo los "bonitos"; que el orden de
  la tabla sea siempre el mismo; que ninguna prueba dejara colar un símbolo de moneda por
  descuido), y se añadieron esas pruebas antes de cerrar la tarea.

- **S4.6 — Dominios propios de cliente (alcance acotado)** (24/07/2026): el plan pedía que una
  asesoría pudiera usar su propio dominio (p. ej. `facturas.suasesoria.es`) en vez del
  subdominio de Autoken, con el certificado de seguridad (HTTPS) emitiéndose solo automáticamente
  al apuntar un dominio de verdad. Antes de construir nada se investigó y se confirmó que esta
  tarea tiene dos partes muy distintas: (1) la aplicación reconociendo y guardando ese dominio
  propio — verificable aquí, con pruebas automáticas reales — y (2) la pieza de infraestructura
  real (el servidor que emite certificados solo al detectar tráfico de un dominio real, y
  comprobarlo apuntando un dominio de verdad) — que necesita acceso al servidor de producción y a
  un dominio real apuntándole, algo que este entorno de trabajo no tiene. En vez de fingir esa
  segunda parte, se preguntó a Julio cómo seguir; decidió construir ya la primera parte (con sus
  pruebas automáticas de verdad) y dejar la segunda explícitamente pendiente para una sesión con
  acceso al servidor. Ahora el panel de plataforma permite asignar (o quitar) un dominio propio a
  cada asesoría, y la aplicación ya sabe reconocer a qué asesoría pertenece una petición que llega
  por ese dominio, exactamente igual que ya sabía hacerlo por subdominio. La auditoría (tres
  revisores en paralelo, como siempre) encontró y corrigió 4 problemas reales antes de cerrar la
  tarea: dos de diseño (se podía "asignar" un dominio que en la práctica nunca iba a funcionar
  porque coincidía con uno reservado de la propia plataforma; y al pasar una asesoría de demo a
  real se podía "perder de vista" —aunque no borrar— su dominio propio ya configurado, mostrando
  un dato incorrecto), uno de seguridad (sin protección, cualquiera podía obligar a la aplicación a
  consultar la base de datos una y otra vez mandando peticiones con un dominio inventado distinto
  cada vez — corregido con el mismo mecanismo de caché que ya protegía la resolución por
  subdominio) y uno más grave encontrado en la revisión final: el identificador interno de una de
  las migraciones (los pasos que preparan la base de datos) era demasiado largo para la columna
  donde Postgres guarda ese dato — habría roto la puesta al día de la base de datos en cualquier
  entorno, no solo en pruebas. Corregido y blindado con una prueba que impide que vuelva a pasar.
  También se encontró y corrigió, ya en la verificación final, que cualquier petición con una
  dirección de una sola palabra (como la que usan las pruebas automáticas internas, o un chequeo
  de salud del servidor) generaba una consulta a la base de datos sin ninguna posibilidad de
  encontrar nada — descartada ahora sin tocar la base de datos, porque un dominio propio de verdad
  siempre tiene al menos dos partes (p. ej. `facturas.algo`).

- **S4.7 — Ciclo de vida de una asesoría** (24/07/2026, última tarea del lote S4.4-S4.7): hasta
  ahora no había forma, desde el panel de plataforma, de pausar temporalmente una asesoría sin
  borrar nada, de sacarse una copia completa de sus datos, ni de darla de baja de forma segura.
  Esta tarea cierra las tres piezas que faltaban. **Suspender/reactivar**: un botón que bloquea el
  acceso de todos los usuarios de esa asesoría al instante (sin esperar a que caduque su sesión),
  sin tocar ni un solo dato; reactivar lo revierte. **Exportar**: genera un fichero ZIP descargable
  con una copia completa de todo lo que tiene la asesoría — sus datos (en ficheros de texto, uno
  por cada tipo de información: empresas, usuarios, facturas...) y sus documentos originales
  subidos. **Borrar**: a diferencia de "purgar" (S4.4, que solo podía borrar asesorías de prueba),
  este botón SÍ puede borrar una asesoría real con datos de un cliente — la operación más peligrosa
  de todo el panel hasta ahora. Por eso exige dos cosas antes de dejar borrar: escribir a mano el
  nombre exacto de la asesoría (para no borrar la equivocada por error) y haber hecho antes al
  menos una copia de seguridad con el botón de exportar (nunca se puede borrar algo de lo que no
  quede copia). Dado lo delicado de esta tarea, la auditoría se hizo con especial cuidado en la
  parte de seguridad: confirmó que es imposible borrar sin que ambas condiciones se cumplan de
  verdad (comprobado línea a línea, incluido qué pasa si dos personas intentan borrar la misma
  asesoría al mismo tiempo) y no encontró ningún fallo grave. Sí encontró y se corrigió un fallo
  real de otro tipo: si se pedía exportar la misma asesoría dos veces muy seguidas, la segunda
  copia podía sobrescribir a la primera en silencio sin avisar de nada — ahora cada copia queda
  guardada por separado. También se reforzaron los botones del panel (habían crecido demasiado
  juntos en una sola pantalla) separándolos en piezas más pequeñas y manejables.

- **S4.9 — App-shell: login real, menú y navegación** (24/07/2026, primera tarea del lote de cierre
  de backlog previo al Sprint 5, decidida junto con Julio): hasta ahora la aplicación tenía 5
  pantallas completas y probadas (historial, confirmación, panel de facturas, empresas, plataforma)
  pero **no había ninguna forma de llegar a ellas** — no existía pantalla de login, ni menú, ni
  manera de pasar de una a otra con el ratón; lo que se veía al abrir la aplicación seguía siendo la
  pantalla de comprobación técnica de la Fase 0. Esta tarea construye el "esqueleto" que faltaba:
  una pantalla de inicio de sesión de verdad (con su segundo factor de verificación si el usuario lo
  tiene activado), un menú superior que muestra solo las pantallas que le corresponden a cada tipo
  de usuario (una asesoría no ve el panel de plataforma; el panel de plataforma no ve las pantallas
  de una asesoría), y navegación real entre pantallas (p. ej. desde "Empresas", el botón "Ver
  facturas" ahora sí lleva de verdad al panel de facturas de esa empresa). También resuelve algo
  invisible pero importante: mantener la sesión activa de forma segura. La "llave" de acceso vive
  solo en la memoria del navegador mientras se usa la aplicación (nunca guardada en el disco del
  ordenador, para que no se pueda robar de ahí); si esa llave caduca a media sesión, la aplicación la
  renueva sola por detrás sin interrumpir a quien la está usando, y solo si esa renovación falla de
  verdad se le pide volver a iniciar sesión. Al cerrar sesión, todo rastro de esa llave se borra al
  instante. La antigua pantalla de comprobación técnica de la Fase 0 (que ya no tenía ningún uso real
  una vez la aplicación tiene pantallas de verdad) se retiró en esta misma tarea.
- **Pendiente transversal detectado el 23/07/2026 → RESUELTO por S4.9** (ver entrada de arriba).

- **S2.2 — Captura guiada de fotos desde el móvil** (24/07/2026, segunda tarea del lote de cierre de
  backlog, cierra el último hueco de Sprint 2): hasta ahora no había ninguna forma real de subir una
  factura nueva desde el móvil. Esta tarea añade la pantalla "Subir factura", nueva en el menú y
  además la primera pantalla que ve un usuario raso al iniciar sesión (antes era el historial: subir
  facturas es su tarea del día a día, no consultarlas). Pide la cámara trasera del móvil y muestra
  la imagen en vivo dentro de un marco guía; si la foto sale bien enfocada y se reconoce un
  documento dentro del marco, **se hace la foto ella sola**, sin tener que pulsar nada — y si sale
  borrosa o no hay nada reconocible, sigue esperando en vez de hacer una foto mala. También se puede
  forzar la foto a mano en cualquier momento. Tras capturarla, si se detectan los 4 bordes del
  documento, la aplicación **recorta y endereza la imagen sola** (como si se hubiera escaneado en
  plano, no fotografiado en ángulo) usando una librería de visión por ordenador (OpenCV, la misma
  que usan miles de aplicaciones de escaneo de documentos) que corre entera dentro del propio
  navegador del móvil, sin mandar nada a ningún servidor externo para ese paso. Antes de subir nada,
  siempre se enseña la foto ya procesada para que la persona la revise y decida si la usa o repite —
  nunca se sube una foto sin que alguien la haya visto antes. Si el móvil no da permiso de cámara (o
  el navegador no la soporta), la aplicación ofrece el selector de foto normal del sistema operativo
  como alternativa, sin quedarse bloqueada. Un detalle técnico importante para el resto del
  proyecto: esta es la primera vez que se prueban de verdad, con imágenes reales (generadas por
  código, no fotos guardadas en el repo), los algoritmos de nitidez y detección de bordes — no solo
  que "no fallan", sino que de verdad distinguen una foto nítida de una borrosa y encuentran las
  esquinas de un documento cuando existen. **Verificación pendiente**: como este entorno de trabajo
  no tiene un móvil ni un navegador con cámara real, la comprobación final en un Android/iPhone de
  verdad queda pendiente de que Julio la pruebe tras el despliegue (mismo caso que la infraestructura
  real de S4.6).

- **S4.10 — El interruptor solo-para-Julio** (25/07/2026, tercera y última tarea del lote de cierre de
  backlog previo al Sprint 5): las dos próximas mejoras del lector automático (S2.9/S2.10, realzar la foto
  antes de leerla; S4.8, comparar varios "lectores de IA" a la vez) cuestan dinero real cada vez que se
  usan, así que antes de construirlas hacía falta un interruptor para poder apagarlas de golpe si el gasto
  se dispara — y que solo Julio (o Alberto) pueda tocarlo, nadie más. Esta tarea construye exactamente eso,
  sin encender todavía ninguna de las dos mejoras: una nueva pantalla "Ajustes" dentro del panel de
  plataforma, que solo aparece en el menú de la cuenta que tenga marcada la casilla especial "admin-tech" —
  ni siquiera Julio la ve si esa casilla no está marcada en su cuenta. Esa casilla es a propósito imposible
  de marcar desde la propia aplicación (para evitar que alguien se la active a sí mismo por error o por
  malicia): solo se puede activar entrando directamente a la base de datos, algo que solo hace el equipo
  técnico. Una vez revisado el trabajo, se hizo una limpieza de código (sin cambiar nada de lo que ve el
  usuario): había tres sitios donde el código mezclaba dos trabajos distintos en uno — por ejemplo, la
  pieza que "decide si dejas pasar la petición" también iba a buscar el dato a la base de datos ella misma,
  en vez de que otra pieza se lo trajera ya preparado. Tenerlo mezclado dificulta mantener y revisar ese
  código con el tiempo; separarlo no cambia lo que hace la aplicación, la deja más ordenada por dentro. Se
  comprobó con las **554 pruebas automáticas del motor + las 184 de las pantallas**, todas en verde, que
  nada se rompió con esa limpieza.

- **S2.9/S2.10 — Realzar la foto y comprobar si de verdad ayuda** (25/07/2026, segunda pieza del lote
  de coste acotado): muchas facturas llegan fotografiadas con el móvil con poca luz o poco contraste.
  La idea es sencilla: antes de que el lector de IA lea la foto, se le puede aplicar un pequeño
  "retoque" automático (más contraste, más brillo, un poco más de color) — como el filtro que mejora
  una foto en el móvil, pero pensado para que un texto se lea mejor, no para que quede bonita. El
  problema es que nadie sabe de antemano si ese retoque ayuda de verdad o no — podría incluso
  empeorar la lectura en algunos casos. Así que en vez de asumirlo, la aplicación ahora puede leer
  **las dos versiones de la misma foto** (la original y la retocada) y anotar cuál acertó más datos,
  usando las mismas comprobaciones matemáticas que ya usa para decidir si una factura necesita
  revisión (que el NIF cuadre, que las cuentas salgan). Nunca "opina" una IA sobre cuál es mejor — se
  cuenta objetivamente. Esto cuesta dinero real cada vez que se hace (se le pide al lector que lea dos
  veces en vez de una), así que **está apagado por defecto** y solo se enciende con el interruptor que
  ya construyó S4.10 — mientras esté apagado, no cambia nada ni cuesta nada. También se construyó (sin
  ejecutarlo) un mecanismo para aplicar esto retroactivamente a las facturas ya existentes, cuando
  Julio decida que merece la pena gastar en ello. La revisión final antes de cerrar la tarea encontró
  y corrigió un fallo real de diseño: la primera versión pedía la lectura "original" **dos veces** en
  vez de reutilizar la que ya se había hecho — con el interruptor encendido, cada factura iba a costar
  el **triple** de lo previsto en vez del doble. También se blindó contra un fichero de imagen
  "trampa" (unas dimensiones declaradas absurdamente grandes que podrían agotar la memoria del
  servidor al intentar abrirlo) y se movió el trabajo pesado de retocar la imagen fuera del camino
  principal, para que una factura problemática no ralentizara el procesamiento de las demás asesorías
  a la vez. 554 pruebas automáticas previas + 20 nuevas, todas en verde.

- **S4.8 — Comparar varios "lectores de IA" a la vez** (25/07/2026, última tarea del lote de cierre
  de backlog previo al Sprint 5, con el alcance completo que pidió Julio): igual que S2.9/S2.10
  comparaba "la foto original" contra "la foto retocada", esta tarea compara **6 lectores de IA
  distintos** leyendo la misma factura (Gemini en dos versiones, Claude, un modelo de OpenAI, el
  lector especializado en facturas de Microsoft, y un OCR puro de Mistral), para saber con datos
  reales cuál acierta más antes de decidir con cuál quedarse en producción. Hay un matiz importante:
  no todos son iguales por dentro. Cuatro de ellos son "se les puede preguntar" (se les manda la
  imagen y un texto pidiéndoles que devuelvan los datos en un formato concreto); pero el lector de
  Microsoft tiene su propio formato fijo de respuesta (hay que "traducirlo" al formato común de la
  aplicación) y el de Mistral es un OCR puro — solo transcribe el texto que ve, no entiende qué es
  "la fecha" o "el importe", así que sus resultados siempre salen vacíos en los campos concretos, **a
  propósito, no por un fallo**: el panel ahora avisa de esto junto al nombre de esos dos motores para
  que no se lea como si hubieran fallado. Igual que S2.9/S2.10, todo esto está detrás del mismo
  interruptor de S4.10, apagado por defecto: mientras esté apagado no cuesta nada. Un nuevo panel
  "Ranking OCR", visible solo con el interruptor encendido, muestra por cada motor cuántas facturas
  ha leído, su puntuación media, y en cuántas quedó en primer puesto (un empate cuenta para los dos
  motores empatados, nunca se inventa un ganador único).

  **Un incidente real durante la construcción de esta tarea, contado con total transparencia**: en
  un momento del desarrollo, una prueba automática con el interruptor encendido se ejecutó sin
  indicarle explícitamente qué "lectores de mentira" usar para la prueba — y el código, al no
  recibir nada, construyó los 6 lectores REALES a partir de las claves configuradas en este entorno
  de trabajo (que sí tiene credenciales de verdad de los 6 proveedores), y les mandó una imagen de
  prueba sin sentido. Esto disparó de verdad 6 llamadas de pago reales, de coste pequeño y acotado,
  a los 6 proveedores. Se avisó a Julio de esto en el momento en que ocurrió. Corregido de raíz, no
  solo parcheado: ahora la única pieza del código con permiso para "si no te dicen qué usar,
  construye los lectores reales" es la pieza principal del trabajador OCR en producción — ninguna
  otra pieza interna tiene ese permiso, así que una prueba futura que se olvide de indicar los
  lectores de mentira simplemente falla al momento en vez de arriesgarse a llamar a algo real. La
  revisión final encontró además, por su cuenta, un segundo bug de coste real: el lector "por
  defecto" (Gemini) se estaba llamando **dos veces** por factura (una para el resultado normal, otra
  para el ranking) en vez de reutilizar la lectura que ya se había hecho — el mismo tipo de fallo que
  ya se había corregido en S2.9/S2.10, colado de nuevo aquí sin querer. Ya corregido. 623 pruebas
  automáticas del motor + 191 de las pantallas, todas en verde.

**Con S4.8 cerrado, el lote de cierre de backlog previo al Sprint 5 queda COMPLETO**: S4.9
(app-shell), S2.2 (captura guiada), S4.10 (interruptor admin-tech), S2.9/S2.10 (realce + comparativa)
y S4.8 (ranking multi-modelo), las 5 tareas cerradas y mergeadas.

- **S5.1 — Candados extra y freno a los abusos** (25/07/2026, primera tarea del Sprint 5, el sprint
  de "blindar antes de salir a producción"): dos mejoras de seguridad que no cambian nada de lo que
  ve el usuario normal, pero cierran huecos reales. Primero, dos cabeceras HTTP nuevas que le dicen
  al navegador "esta página no debe poder ser abierta como ventana emergente desde otra web ni
  usada como recurso incrustado desde otra web" — protección de bajo coste contra una familia de
  ataques de robo de información entre pestañas (parecido a poner un candado extra en una puerta
  que ya tenía cerradura, por si acaso). Segundo, y más importante: se descubrieron dos puertas de
  la aplicación que hasta ahora no tenían ningún freno frente a quien las golpea sin parar. Una es
  la confirmación del código de seis dígitos al activar una cuenta nueva (nadie limitaba cuántas
  veces se podía intentar adivinarlo); la otra es la renovación automática de la sesión (nadie
  limitaba cuántas veces se podía intentar con una cookie inventada). Ahora las dos tienen el mismo
  tipo de freno que ya protegía el login desde el principio del proyecto: pasados unos intentos
  fallidos, toca esperar. La revisión final, antes de cerrar la tarea, encontró y corrigió dos
  fallos de diseño reales y sutiles: el freno de activación, tal y como se construyó al principio,
  dejaba adivinar sin límite si el código de seis dígitos que se probaba pertenecía a un usuario que
  NO existe (solo contaba los intentos contra cuentas reales) — un atacante podría haber usado esa
  diferencia para averiguar qué códigos de activación son de verdad, aunque en la práctica sea casi
  imposible de explotar por lo largos que son. Y el freno de la renovación de sesión, copiado tal
  cual del de login, se olvidaba de "aflojar" cuando alguien renovaba con éxito — así que, en una
  oficina donde muchas personas comparten la misma conexión a internet, los fallos normales de unos
  (una sesión caducada, por ejemplo) podían acabar bloqueando también a los demás. Los dos quedaron
  corregidos antes de cerrar. 631 pruebas automáticas del motor, todas en verde.

- **S5.6 — Que alguien se entere si algo va mal** (26/07/2026, segunda tarea del Sprint 5): hasta
  ahora, si el servicio caía, se llenaba el disco del servidor, o las facturas se quedaban
  atascadas esperando a ser leídas, nadie se enteraba hasta que un cliente se quejaba. Esta tarea
  construye dos cosas. Primero, un "termómetro" nuevo: la aplicación ahora publica en una dirección
  interna (`/metrics`) cuántas peticiones está recibiendo, cuántas fallan, y cuántas facturas
  llevan esperando a que un motor de IA las lea (y desde cuándo la más antigua). Segundo, la
  maquinaria completa para vigilar ese termómetro y avisar sola: Prometheus (lo lee cada 15
  segundos), Grafana (lo dibuja en un panel visual) y Alertmanager (decide a quién avisar si algo
  se sale de lo normal — el servicio caído, muchos errores seguidos, facturas atascadas más de 10
  minutos, o el disco por debajo del 10% libre). Está todo construido y probado, pero **todavía no
  encendido de verdad**: hace falta desplegarlo en el servidor real (sesión futura, como el
  certificado de dominio propio de S4.6) y que Julio decida a qué correo o canal llegan los avisos.
  También queda preparado (pero apagado) un servicio externo, Sentry, que guardaría el detalle
  técnico de cada error para poder investigarlo después — se activará cuando Julio se cree una
  cuenta, sin coste mientras tanto. La revisión final encontró y corrigió un fallo de diseño real:
  el "termómetro" apuntaba el método de cada petición web (GET, POST...) tal cual llegaba, y como
  ese dato lo puede inventar cualquiera que llame a la aplicación, alguien podría haber mandado
  miles de peticiones con métodos inventados distintos para ir llenando la memoria del servidor
  poco a poco — corregido para que solo cuenten los métodos reales que la aplicación usa, y todo lo
  demás se agrupe junto. 638 pruebas automáticas del motor, todas en verde.

- **S5.2 — Cerrar con llave los datos sensibles dentro de la propia base de datos** (26/07/2026,
  tercera tarea del Sprint 5, la más delicada del proyecto hasta ahora): hasta ahora, el CIF y el
  nombre de cada empresa y de cada proveedor/cliente vivían "en abierto" dentro de la base de
  datos — cualquiera con acceso directo a esa base (una copia de seguridad mal guardada, un acceso
  indebido al servidor) los vería sin esfuerzo. Esta tarea los cifra de verdad: cada asesoría tiene
  su propia "llave" para leerlos, calculada al vuelo a partir de un único secreto maestro guardado
  fuera de la base de datos — no existe una tabla de llaves que alguien pudiera robar. Como un CIF
  cifrado ya no se puede comparar directamente (cada vez que se cifra el mismo valor sale distinto,
  a propósito, para que sea más seguro), se guarda además una "huella" del CIF, calculada con la
  misma llave secreta, que sirve para buscar "¿existe ya este CIF?" sin necesidad de descifrar nada
  — el nombre no lleva huella, así que ya no se puede buscar por un trozo de nombre en el panel de
  facturas (antes sí se podía); a cambio, se puede filtrar por un CIF exacto, decisión que tomó
  Julio en persona tras planteársela: prefirió mantener el nombre cifrado de verdad antes que
  sacrificar esa protección por conservar una búsqueda menos importante. El histórico de facturas
  ya guardadas se migró automáticamente a este nuevo formato sin perder ni un dato. También se
  construyó (aunque no hace falta usarlo salvo sospecha) un script para "cambiar la llave maestra"
  de golpe en toda la aplicación, con su propio manual de uso paso a paso.

  **Un hallazgo real de transparencia, contado tal cual ocurrió**: durante el desarrollo, un error
  de programación (no relacionado con la seguridad en sí) hizo que, al validar un fichero de
  configuración de infraestructura, apareciesen en la propia conversación de trabajo dos claves
  reales de proveedores externos (Azure y Mistral) que ya estaban en el servidor de desarrollo —
  sin que se hiciera ninguna llamada externa con ellas, solo se "leyeron por pantalla" sin querer.
  Se avisó a Julio en el momento y se le recomendó rotarlas por precaución.

  **La revisión final, la más exhaustiva del proyecto hasta ahora dado lo delicado del tema,
  encontró y corrigió varios fallos reales, dos de ellos serios**: primero, el "plano" interno de
  cómo debía verse la base de datos (usado por una herramienta de comprobación automática) se había
  quedado desactualizado tras el cambio — nadie lo habría notado hasta que, mucho más adelante,
  alguien pidiera a esa herramienta que generara un cambio nuevo, momento en el que habría
  propuesto **deshacer el cifrado sin darse cuenta**. Corregido y vuelto a comprobar. Segundo, si
  alguna consulta a la base de datos fallaba por cualquier motivo normal (una desconexión, un
  bloqueo pasajero), el mensaje de error interno incluía sin querer la llave secreta usada en esa
  consulta — cerrado para que esa información nunca aparezca en ningún registro. Tercero, se
  encontró y corrigió una manera concreta (poco probable, pero real) en la que dos operaciones
  escribiendo a la vez durante un cambio de llave maestra podrían dejar un dato ilegible para
  siempre; ahora el manual de esa operación exige detener la aplicación un momento mientras dura el
  cambio, precisamente para que eso no pueda pasar — y, comprobando esa misma pieza a fondo, salió
  a la luz un cuarto fallo, independiente: el historial de "quién cambió qué en una factura ya
  confirmada" está diseñado para que NADIE pueda alterarlo después de escrito (ni siquiera la propia
  aplicación) — al intentar cambiarle la llave de cifrado a esos registros antiguos, el sistema
  correctamente se negó, y hubo que abrirle un permiso muy concreto y limitado (solo para esas dos
  columnas cifradas, nunca para el resto del historial, que sigue siendo intocable). Se detectó
  además que dos paneles de experimentos de comparación de motores de IA (S2.9/S2.10 y S4.8, ambos
  apagados por defecto) guardan el CIF/nombre sin cifrar dentro de un dato más grande — queda
  anotado como pendiente de decidir con Julio antes de encenderlos alguna vez en producción, no
  como un descuido. 655 pruebas automáticas del motor + 191 de las pantallas, todas en verde.

- **S5.4 — Ponerse en la piel de alguien que intenta romper la aplicación** (26/07/2026, cuarta
  tarea del Sprint 5): a diferencia de las tareas anteriores, aquí no se construyó ninguna
  funcionalidad nueva — se dedicó la sesión a intentar **atacar de verdad** la aplicación ya
  construida, como haría alguien de fuera sin ver el código, siguiendo una checklist estándar de la
  industria (OWASP Top 10: control de acceso roto, inyección, fallos de autenticación, ficheros
  subidos maliciosos). Antes de lanzar un solo ataque, se repasó a fondo qué defensas ya existían
  de tareas anteriores — y resultó ser mucho: cada tarea de este proyecto termina con una revisión
  de seguridad, así que ya había protección real contra casi todo lo típico. Con eso claro, el
  esfuerzo se centró en cuatro ataques concretos que nadie había probado todavía de verdad: (1)
  fabricar a mano credenciales de acceso falsificadas de varias formas distintas (una sin firma en
  absoluto, una del tipo equivocado, una firmada con una clave inventada, una caducada) para
  confirmar que la aplicación las rechaza todas sin excepción; (2) disparar **dos peticiones para
  renovar la sesión al mismo tiempo, de verdad** con la misma credencial de renovación, para
  comprobar que exactamente una tiene éxito y la otra falla — un tipo de fallo que solo se ve
  provocando la carrera de verdad, nunca leyendo el código con calma; (3) hacer que dos asesorías
  distintas importen una empresa con el mismo CIF a la vez, para confirmar que no se mezclan ni
  chocan entre sí; (4) comprobar que meter código malicioso típico de bases de datos en un campo de
  texto normal (nombre de empresa, email de alta) se trata como texto inofensivo, nunca como una
  orden que se ejecuta. **El resultado real de este pentest fue que las cuatro pruebas pasaron sin
  tener que tocar ni una línea del código de la aplicación** — todas las protecciones que ya se
  habían construido en tareas anteriores aguantaron el ataque tal cual estaban. Es un resultado
  bueno y real (no es "no se hizo nada"): significa que el trabajo de seguridad de las tareas
  anteriores estaba bien hecho. 663 pruebas automáticas del motor, todas en verde (las 655 de
  antes + 8 nuevas de este pentest).

- **S5.5 — Comprobar que la aplicación aguanta cuando varias personas suben facturas a la vez**
  (26/07/2026, quinta tarea del Sprint 5): antes de que esto vaya a producción hay que saber si
  aguanta el pico real de una asesoría (varios empleados subiendo facturas al final de mes), no
  suponerlo. Se instaló una herramienta de prueba de carga (k6) y se lanzaron **50 subidas de
  facturas reales a la vez** contra la aplicación funcionando de verdad (con su base de datos, su
  almacén de ficheros y su caché reales, sin gastar dinero en IA porque el robot que lee las
  facturas estaba apagado durante la prueba). **El resultado fue un fallo real y medible**: 43 de
  las 50 peticiones se quedaban colgadas hasta 32 segundos y acababan fallando. La causa: la
  aplicación mantiene un "grupo" de conexiones ya abiertas a la base de datos para no tener que
  abrir una nueva en cada petición (abrir una es caro); ese grupo tenía sitio para solo 15
  conexiones simultáneas, y cada subida de factura ocupa una conexión durante varios pasos
  seguidos (comprobar que la factura no está duplicada, guardarla) — con 50 subidas a la vez, se
  llenaba enseguida y las peticiones de más se quedaban esperando en cola hasta agotar la
  paciencia y fallar. Se corrigió ampliando ese grupo a un tamaño más generoso (configurable, no
  un número fijo escondido en el código) y se **repitió la misma prueba** para comprobar que de
  verdad se había arreglado, no solo de teoría: la segunda vez, las 50 peticiones tardaron entre 1
  y 3 segundos cada una y ninguna falló. Un dato curioso durante la comprobación: en una prueba
  intermedia salieron 7 "fallos" que resultaron no ser fallos de verdad, sino la propia aplicación
  rechazando subir dos veces la misma factura (protección que ya existía) porque esos ficheros ya
  se habían subido con éxito en la prueba anterior al arreglo — se comprobó el motivo exacto de
  cada fallo antes de dar la tarea por buena, para no confundir "la app protegiéndose bien" con
  "la app rota". 663 pruebas automáticas del motor, todas en verde.

- **S5.3 — Copias de seguridad de la base de datos, probadas de verdad** (26/07/2026, sexta y
  última tarea del Sprint 5, SPRINT 5 COMPLETO): antes de esta tarea no había ningún mecanismo real
  de copia de seguridad. El plan pedía "backup nocturno cifrado a Hetzner" (un servicio externo de
  almacenamiento), pero en este entorno de trabajo no hay ninguna cuenta de Hetzner real todavía —
  se le preguntó a Julio antes de construir nada, y decidió: construir la máquina completa (copiar +
  cifrar + comprobar que la copia sirve de verdad) y dejar el "enviarla a Hetzner cada noche" para
  cuando exista esa cuenta real, exactamente igual que se hizo antes con los dominios propios (S4.6)
  o el panel de monitorización (S5.6). Se construyó: un volcado completo de la base de datos, cifrado
  con una contraseña (para que, si alguien roba el fichero de la copia, no pueda leer nada sin esa
  contraseña) DISTINTA de la que ya protege el CIF/nombre de las empresas (S5.2) — dos candados
  separados, para que perder la llave de uno no abra el otro. Y lo más importante: no basta con
  "hacer la copia", hay que demostrar que **se puede recuperar de verdad**. Se hizo un "simulacro de
  restauración" real: coger la copia cifrada, descifrarla, reconstruirla en una base de datos nueva y
  vacía, y comprobar que todos los datos vuelven exactamente igual (incluidas las columnas cifradas).
  Medido de verdad: la copia de 20 asesorías de prueba tardó **0.35 segundos**, y reconstruirla desde
  cero tardó **1.1 segundos**.

  **En cristiano sobre lo que encontró la revisión de tres perspectivas**: dos fallos seguidos que
  merece la pena explicar porque son sutiles. El primero: la contraseña de acceso a la base de datos
  (la que usa la copia de seguridad para poder leer TODA la información de TODAS las asesorías, no
  solo la tuya) se pasaba de una forma que cualquiera con acceso al mismo ordenador podría haber
  visto de refilón mientras la copia se estaba haciendo — como escribir tu contraseña en un post-it
  pegado al monitor en vez de guardarla en la cabeza. Se corrigió pasándola por un canal que solo el
  propio proceso puede leer. El segundo, más interesante: la comprobación de "¿esta contraseña de
  backup es lo bastante fuerte?" se había puesto en el sitio donde arranca TODA la aplicación (no
  solo la herramienta de backup) — lo que significaba que, sin querer, habría que ponerle esa
  contraseña también a la parte de la aplicación que atiende a los usuarios normales por internet,
  aunque esa parte nunca la necesita. Es como exigir que el portero de un edificio lleve también la
  llave de la caja fuerte del banco de al lado, solo porque ambos edificios comparten la misma
  entrada de suministros: si alguien engaña al portero, ahora también tiene la llave de la caja
  fuerte, sin necesidad. Se corrigió para que solo la propia herramienta de backup (nunca la parte
  pública de la aplicación) tenga esa comprobación. 683 pruebas automáticas del motor, todas en
  verde.

## 5. Qué queda por delante

- **Sprint 3 completo** (S3.1-S3.5 cerrados 23/07/2026). Queda pendiente el frontend de la edición de
  facturas (S3.3 solo trajo la capacidad de corregir con seguridad, no la pantalla para hacerlo cómodo),
  si hace falta más adelante.
- **Sprint 4 COMPLETO** (S4.1-S4.7 cerrados 24/07/2026 — panel de plataforma + white-label + PWA
  multi-tenant). S4.6 se cerró con alcance acotado (ver entrada de arriba): la mitad de
  infraestructura real (el servidor emitiendo certificados de un dominio de verdad) queda
  pendiente de una sesión futura con acceso al servidor de producción/staging y a un dominio real
  — dominio ya reservado para esa prueba: `setex-facturas.autoken.es`.
- **Sprint 2 COMPLETO** con el cierre de S2.2 (24/07/2026) — verificación en dispositivo real
  pendiente (ver entrada de arriba), igual que la infra de S4.6.
- **Lote de cierre de backlog previo al Sprint 5 — COMPLETO** (decidido con Julio el 24/07/2026):
  las 5 tareas (S4.9 app-shell, S2.2 captura guiada, S4.10 interruptor admin-tech, S2.9/S2.10
  realce+comparativa, S4.8 ranking multi-modelo) cerradas y mergeadas el 25/07/2026.
- **Sprint 5 (hardening+QA) COMPLETO** (25-26/07/2026, orden acordado con Julio): las 6 tareas —
  S5.1 (cabeceras y límites), S5.6 (monitorización y alertas), S5.2 (cifrado por tenant), S5.4
  (pentest propio), S5.5 (pruebas de carga) y S5.3 (backups + restore drill) — cerradas y mergeadas.
  Tres piezas de infraestructura real quedan explícitamente pendientes de sesiones futuras con acceso
  a esa infraestructura (mismo patrón en las tres, decisión de alcance ya confirmada por Julio en cada
  una, no bloquean el roadmap): el stack de monitorización de S5.6 (Prometheus/Grafana/Alertmanager)
  está construido pero no desplegado de verdad contra la VPS B; el cron nocturno real + la subida a un
  destino externo (Hetzner) de S5.3 está construido y probado pero no conectado a un destino real; el
  script de rotación de clave de S5.2 no se ha ejecutado nunca contra datos reales (no hace falta
  salvo sospecha de filtración).
- **Fase de despliegue**: el día que Setex (la v1 actual) se apaga y todo el mundo pasa a usar esta versión
  nueva.

**Avance estimado hacia producción a día de hoy: ≈83%** (43 de 53 tareas del plan "core" completas
del todo — S4.9 es una tarea nueva, no estaba en el recuento original de 51, añadida para cerrar el
hueco de integración detectado el 23/07/2026 — sin contar el módulo de Verifactu ni la limpieza
final del servidor viejo, que van en paralelo y no bloquean el lanzamiento). **Sprint 2, Sprint 3,
Sprint 4 y Sprint 5 completos. Lote de cierre de backlog previo al Sprint 5 COMPLETO. Siguiente: la
Fase de Despliegue (go-live y migración de Setex) — ver PLAN MAESTRO.**

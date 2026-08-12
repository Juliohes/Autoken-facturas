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

- **Primer despliegue real de verdad, en la máquina de verdad** (27/07/2026): hasta ahora todo lo
  construido se había probado contra bases de datos y servidores de prueba, nunca puesto a
  funcionar de verdad en la máquina donde algún día atenderá a usuarios reales. Esta vez sí: se dejó
  la aplicación completa (con su base de datos, su cola de trabajos, su almacén de ficheros)
  funcionando de verdad en la VPS B, con una dirección web real y un candado (HTTPS) real y válido
  emitido por una autoridad de verdad (Let's Encrypt) — no un candado de prueba. También se dejó
  funcionando de verdad el panel de vigilancia (el "S5.6" de antes): ahora hay un ordenador
  observando la aplicación real, con las 4 alarmas configuradas todas en estado saludable.
  Descubrimiento curioso por el camino: la propia sesión de trabajo donde se ha construido casi todo
  este proyecto ha resultado ser, sin saberlo hasta ahora, la propia máquina de destino — no un
  simulacro aparte, como se pensaba.

  Al intentar encenderlo de verdad aparecieron 3 averías reales que ninguna prueba automática podía
  haber visto antes (solo se ven encendiendo el motor real, no con el motor de pruebas): la más
  importante, un lío de nombres que hacía que la "llave maestra" de la base de datos y la "llave del
  día a día" de la aplicación fueran sin querer la misma persona — como si el guardia de seguridad
  del banco y el cajero fueran la misma persona con la misma llave, cuando deberían ser distintos.
  El propio sistema de seguridad ya construido en una tarea anterior (S5.2) lo detectó solo y se
  negó a arrancar, exactamente para eso está — se corrigió separando de verdad ambas llaves. Las
  otras dos eran más pequeñas: una carpeta mal colocada que impedía arrancar el panel de vigilancia,
  y una señal despistada que hacía que el "portero" (Traefik, quien dirige el tráfico a la puerta
  correcta) mirara por la ventana equivocada.

- **El "comedor" (la pantalla visual), añadido el mismo día**: tras dejar la cocina funcionando
  (entrada anterior), Julio pidió también la parte que se ve — la pantalla con la que un usuario
  real entraría a subir facturas o ver el panel. Se metió en la misma dirección web
  (`panel-staging.autoken.es`): quien pida algo que empiece por `/api/` sigue yendo a la cocina
  (el motor), y todo lo demás va a la pantalla visual, siguiendo exactamente el mismo reparto que ya
  usaba de antes la web corporativa de Autoken (que resultó estar viviendo, sin que nadie lo supiera
  hasta ahora, en esta misma máquina). Verificado con la propia página cargando de verdad en el
  navegador.

- **La copia de seguridad, funcionando de verdad, con un descubrimiento curioso** (27/07/2026):
  Julio contrató una VPS de Hostinger para guardar ahí las copias (no Hetzner, para tener todo con
  el mismo proveedor). Al conectarse a ella se descubrió que no era una máquina nueva y vacía, sino
  una que Julio ya usaba para otras cosas suyas (una herramienta de transcripción, un proyecto
  llamado "brand-brain", entre otros) — con espacio de sobra igualmente para lo que necesitamos
  (las copias de la base de datos pesan poco). Se hizo la prueba completa de verdad: generar la
  copia cifrada, subirla a esa otra máquina, bajarla de vuelta, y reconstruir con ella una base de
  datos nueva desde cero — comprobando que los datos vuelven exactamente igual. Se dejó también
  programado que esto se repita solo, cada noche a las 3 de la madrugada.

  Al hacer esta prueba de verdad (no solo en teoría) salió un fallo real curioso: la herramienta que
  usa el ordenador para hablar con la base de datos venía en una versión más nueva (v17) que la
  propia base de datos (v16) — como intentar leer un documento con una versión de Word demasiado
  moderna para el ordenador que lo abre. Al reconstruir la copia con esa herramienta demasiado
  nueva, fallaba con un mensaje sobre un ajuste que la versión vieja no reconocía. Se corrigió
  instalando la herramienta en la versión exacta que corresponde (v16), descargada directamente de
  la fuente oficial de PostgreSQL en vez de la que trae el sistema operativo por defecto.

- **"Se ve fatal" — arreglado, con la marca real de Autoken** (27/07/2026): Julio entró por
  primera vez en la app de verdad y avisó de algo importante: los nombres y textos se veían casi
  invisibles, letras gris clarito sobre un fondo blanco. La causa: quien construyó cada pantalla
  (en tareas de hace semanas) daba por hecho que habría un fondo oscuro detrás — como escribir con
  tiza blanca pensando que la pizarra es negra — pero nadie había puesto ese fondo oscuro de verdad
  en el "marco" que envuelve a todas las pantallas ya dentro de la app (solo la pantalla de
  "iniciar sesión" tenía el suyo propio, aparte). Se corrigió poniendo ese fondo en el sitio común
  correcto, para que todas las pantallas lo hereden a la vez.

  Aprovechando que había que tocar los colores, se metieron también los colores REALES del logo de
  Autoken (azul marino oscuro + naranja, mirando directamente los ficheros de la web
  `autoken.es` — que resulta que vive en esta misma máquina) en vez de los verdes/grises genéricos
  que había puesto quien construyó cada pantalla al principio, sin pensar en una marca concreta
  todavía. Como casi todas las pantallas ya usaban los mismos dos "botes de pintura" de siempre,
  bastó con cambiar el contenido de esos dos botes para que toda la aplicación cambiara de aspecto
  de golpe, sin tener que repintar pantalla por pantalla. También se puso el logo real de Autoken
  por defecto (antes no había ninguno). Comprobado con capturas de pantalla reales de la propia
  aplicación funcionando, antes y después.

- **Las empresas reales, en el sitio correcto: `setex`, no `ilex`** (27/07/2026): se habían cargado
  las 61 empresas reales (nombre y CIF) del Excel que entregó Julio en el tenant equivocado —
  `ilex`, pensado como demo/pruebas vacías, no como el sitio de datos reales. Julio lo pilló al
  vuelo: los datos reales de la gestoría **Setex** (la aplicación "de toda la vida" que este
  proyecto está construido para sustituir) tienen que vivir en su propio tenant, `setex`, con su
  propia dirección `setex.autoken.es` (que ya estaba reservada desde el principio del proyecto,
  justo para esto). Se corrigió: se creó el tenant `setex` de verdad, se le abrió su propia puerta
  de entrada (el mismo mecanismo de siempre, un "cartel" más en el portero automático que ya
  reparte el tráfico entre inquilinos), se movieron las 61 empresas de `ilex` a `setex` (descifradas
  y vueltas a cifrar con la clave que le corresponde a cada tenant, nunca mezclando claves), y se
  dejó `ilex` vacío de nuevo, como debía estar. De paso, se conectó la credencial real de Google
  (la que ya se usó meses atrás para comparar motores de OCR) al proceso que lee facturas, para
  poder procesar de verdad las 20 facturas reales que aún faltan por subir.

- **La migración de verdad: los datos reales de Setex, dentro** (28/07/2026): Julio entregó la
  exportación real de la aplicación antigua de Setex (la que se usa hoy en el día a día, y que este
  proyecto sustituirá cuando llegue el momento): 52 empresas de verdad (más afinadas que el Excel de
  61 de la entrada anterior), 9 personas reales con cuenta, y 29 facturas ya revisadas y confirmadas
  por ellos mismos, con sus fotos originales. Había un problema con las contraseñas: la aplicación
  antigua las guarda cifradas con una "receta" (bcrypt) y la nueva usa otra distinta (Argon2)
  — y es imposible, a propósito, convertir una en otra sin conocer la contraseña real de la persona
  (si se pudiera, cifrar contraseñas no serviría de nada). La solución, que usan empresas grandes
  como Dropbox o Slack cuando cambian de sistema: cada persona sigue entrando con su contraseña de
  siempre, sin enterarse de nada raro, y en ese mismo instante, por dentro, la aplicación nueva
  "traduce" su contraseña a la receta nueva y olvida la vieja para siempre. Así nadie tiene que
  aprenderse una contraseña distinta ni se le pide que la escriba en ningún sitio raro. Se
  importaron ya las 52 empresas, las 6 cuentas reales de empleados/clientes (2 personas de la
  gestoría, 4 clientes) y las 29 facturas con sus fotos — comprobado leyendo los datos reales
  descifrados y bajando una de las fotos de verdad del almacén. Quedan 3 cuentas del equipo interno
  de Autoken por decidir con Julio (si deben tener acceso a todo el sistema o no).

- **Las 3 cuentas tech, resueltas, y un "cartero" para dar de alta cuentas nuevas** (28/07/2026):
  Julio decidió cómo repartir las 3 cuentas del equipo interno: Alberto y Julio tienen acceso
  completo a la plataforma (`platform_admin`, ya lo tenían); soporte deja de tenerlo y pasa a ser
  una cuenta normal de prueba, tanto en `setex` como en `ilex`. Para montar esto (y las cuentas de
  administrador de asesoría de Julio/Alberto en cada tenant, sin tocar las de Carlos/Javier, que son
  reales de un cliente) hacía falta algo que no existía: un "cartero" que diera de alta cuentas
  nuevas sin necesidad de tocar la base de datos a mano. Se construyó `scripts/create_account.py`:
  crea la cuenta y entrega un enlace de un solo uso para que cada persona active la suya y elija su
  propia contraseña — nadie, ni el propio Claude Code, puede fijarle la contraseña a otra persona,
  a propósito (así funciona desde el principio del proyecto). Pendiente: ejecutar estos altas contra
  los datos reales de la VPS (el mecanismo ya está construido y con tests, falta desplegarlo).

- **La pestaña del navegador ya lleva el logo de Autoken** (28/07/2026): antes, al abrir la app en
  cualquier tenant sin un logo propio configurado, la pestaña se quedaba con el icono genérico del
  navegador (una decisión tomada a propósito en su momento). Julio pidió tener un logo real ahí;
  ahora usa el mismo logo de Autoken que ya se ve dentro de la app.

- **Las 8 cuentas del equipo, ya activadas de verdad; y dos fallos que solo se ven al probarlo**
  (29/07/2026): se llevó a la VPS real el "cartero" de cuentas (`create_account.py`) que había
  quedado construido pero sin desplegar, y se usó para crear/activar las 8 cuentas decididas ayer:
  Julio y Alberto como administradores de cada asesoría en `setex` e `ilex`, la cuenta de plataforma
  de Alberto reactivada, y soporte como usuario normal de prueba en los dos tenants. Al ir
  activándolas de verdad, con Julio y Alberto probando cada paso, salieron dos cosas que faltaban y
  que ningún test había cazado porque nadie las había necesitado hasta ahora:
  - **No existía forma de cambiar una contraseña ya puesta.** El "cartero" solo sabía dar de alta
    cuentas nuevas; si alguien ya había fijado su contraseña (por error, o porque quería cambiarla),
    no había ningún camino para repetirlo. Se construyó un comando nuevo, `reset-password`, con el
    mismo principio de siempre: borra la contraseña vieja (y el segundo factor, si lo tenía) y deja
    preparado un enlace nuevo de un solo uso para que la persona elija otra ella misma. Ni Claude
    Code ni Julio llegan nunca a ver ni elegir esa contraseña.
  - **Un "usuario normal" necesita tener una empresa asignada para poder entrar** (a diferencia de
    un administrador de asesoría, que ve todas las empresas de su tenant). La cuenta de soporte se
    había creado sin ninguna empresa vinculada: el login funcionaba, pero justo después fallaba con
    "no se pudo cargar la identidad del usuario", porque el sistema no sabía qué datos enseñarle. Se
    creó una empresa "fantasma" (sin ningún dato real, solo para poder probar el panel) en `setex` y
    en `ilex`, y se vinculó soporte a cada una.
  - De paso se descubrió (probando el login por el camino largo, con el navegador) que el
    "Invalid credentials" que le salía a Julio dos veces no era un fallo del sistema: era que la
    contraseña escrita en el comando de activación y la tecleada luego en el navegador no eran
    exactamente la misma cadena de texto (un espacio, una letra, el propio navegador sugiriendo otra
    distinta). Se comprobó el ciclo completo (activar + entrar) de un tirón, sin manos de por medio,
    y funcionó a la primera: la aplicación estaba bien desde el principio.

- **El logo, ida y vuelta** (29/07/2026): Julio pidió quitar el texto "AUTOMATIZACIÓN E IA" del
  logo. El primer intento lo quitó de TODA la app (login, menú, pestaña del navegador), pero el
  texto ahí dentro va bien: solo sobraba en los sitios pequeños, donde no cabe legible. Se corrigió:
  dentro de la app (login, menú) se sigue viendo el logo completo con su texto; solo la pestaña del
  navegador y el icono para "instalar" la app en el móvil llevan el dibujo solo, sin letras. De
  paso se descubrió que ese icono de instalación llevaba años siendo un cuadrado azul liso, sin
  ningún dibujo — ahora lleva el icono real de Autoken.

- **Lote grande de mejoras del panel, "como un profesional"** (01/08/2026): Julio pidió de un
  tirón 14 cambios sobre el panel de plataforma y el de facturas: quitar la columna "Dominio
  propio"; separar administradores de usuarios en las métricas de cada tenant y añadir "facturas
  totales" (antes solo se contaban las procesadas por OCR); poder subir el logo de un tenant como
  imagen de verdad, no solo pegar una URL (para eso se creó el primer bucket público de todo el
  proyecto, de solo lectura, únicamente para logos — nunca para facturas); tablas anchas con
  barra de desplazamiento arriba y abajo en el móvil; los importes siempre con coma decimal
  también al exportar a Excel; quitar la columna "Estado CIF"; y que cada celda de las tablas de
  empresas y facturas se pueda editar de verdad, con historial permanente de cada cambio y opción
  de revertir (como ya existía para las facturas desde antes, aplicado ahora también a empresas).
  Una segunda ronda de ajustes sobre el panel de facturas: quitar el historial y el botón "Editar"
  de cada fila (un único interruptor general de edición para toda la tabla en su lugar); hacer que
  el botón "Ver" enseñe de verdad la foto original de la factura (antes no hacía nada — el enlace
  que generaba apuntaba al almacén interno, inalcanzable desde un navegador real; se cambió para
  que la propia API sirva la imagen); los tramos de IVA como un botón con el número de tramos que
  abre una ventanita editable; y que la tabla muestre también la empresa cliente (quién sube la
  foto), no solo el proveedor de la factura. Verificado en verde y desplegado a producción real.

- **Prueba del diseño de SETEX v1 para el rol "usuario", evaluada y descartada** (01-02/08/2026):
  Julio pidió probar, sin ningún riesgo para lo que ya funciona, un rediseño visual inspirado en la
  aplicación anterior (SETEX v1) para las pantallas que usa un empleado normal (capturar, confirmar,
  historial). Se montó un "probador" totalmente aislado: una rama de código aparte, una web nueva
  (`setex-staging.autoken.es`) con su propio contenedor, que hablaba con los mismos datos reales de
  `setex` pero sin tocar ni un byte de la app real (`setex.autoken.es` seguía funcionando exactamente
  igual todo el tiempo). Julio lo probó y decidió que prefería el diseño anterior. La rama con el
  diseño de SETEX se ha guardado en GitHub, etiquetada como "configuración inicial de setex", por si
  algún día se quiere retomar; el probador se ha apagado.

- **Botones más grandes, subir archivo del dispositivo, y un hueco de seguridad cerrado antes de
  que llegara a pasar** (02/08/2026): sobre la pantalla de captura ya existente (la que Julio
  prefirió), se agrandaron los botones de Recibida/Emitida, el botón de tomar foto y el logo del
  tenant en la cabecera; y se añadió un botón nuevo, "Subir archivo", que abre el buscador de
  ficheros del propio móvil u ordenador (antes esa opción solo aparecía si la cámara fallaba; ahora
  está siempre disponible como alternativa a hacer la foto en el momento). Julio pidió también, de
  forma expresa, una garantía: que ningún empleado pueda ver nunca la foto o los datos de otro
  empleado. Al revisarlo a fondo se encontró que, aunque hoy no pasa con los datos reales (cada
  empresa cliente tiene un único empleado dado de alta), el sistema no lo impedía de verdad: dos
  empleados de la MISMA empresa cliente sí habrían podido ver la foto, el historial y los datos del
  otro, porque el permiso solo comprobaba "misma empresa", no "la misma persona que la subió". Se
  cerró ese hueco en el propio permiso compartido que usan las cuatro pantallas afectadas (ver foto,
  descargar, revisar, confirmar e historial), con pruebas nuevas que demuestran que ahora sí está
  bloqueado, sin tocar en nada lo que ve un administrador de asesoría (que sigue viendo el trabajo de
  todos los empleados de su cartera, como corresponde a su papel).

- **La pantalla de confirmar avisaba mal mientras la IA seguía leyendo la factura** (07/08/2026): al
  subir una foto, la app llevaba al empleado directamente a la pantalla de revisar antes de que la
  lectura automática hubiera terminado, y eso se veía como un error confuso ("no se pudieron cargar
  los datos"). Ahora se ve un mensaje claro de "Procesando factura con IA…" con una ruedecita que se
  actualiza sola; y si la lectura falla de verdad (no solo tarda), el aviso de error llega enseguida
  en vez de hacer esperar más de un minuto en balde.

- **El aviso rojo "No leído" mentía en el importe total y el CIF, dos de los datos más
  importantes** (07/08/2026): Julio detectó que esos dos campos siempre salían marcados como "No
  leído" aunque la IA los hubiera leído perfectamente. La causa: una pieza interna guardaba el nivel
  de confianza de esos dos datos con un nombre distinto al que consultaba la pantalla, así que nunca
  lo encontraba y por defecto asumía lo peor. Arreglado para que el aviso diga la verdad.

- **Rediseño completo de la pantalla de "revisar y confirmar" una factura** (08/08/2026): Julio
  pidió varios cambios juntos sobre la pantalla donde el empleado repasa lo que ha leído la IA antes
  de guardar la factura.
  - **Número de factura**: hasta ahora nadie lo leía, había que teclearlo a mano. Ahora la IA lo lee
    igual que el importe o el CIF, con su propio aviso de fiabilidad.
  - Al construir esto se descubrió que otros dos datos, la base imponible y el IVA, **nunca habían
    tenido ese aviso de confianza propio**: siempre salían en rojo sin importar si estaban bien
    leídos. Julio decidió arreglarlo también: ahora esos dos datos se leen y se puntúan igual que el
    resto.
  - **Tramos de IVA**: antes se editaban en casillas de texto libre, con riesgo de escribir un tipo
    de IVA que no existe en España. Ahora se eligen de una lista cerrada de solo 4 opciones (21%,
    10%, 4% o Sin IVA), con botones para añadir o quitar un tramo.
  - **IRPF**: sigue siendo un dato que rellena el empleado a mano (la IA no lo lee), pero ahora vive
    dentro de un desplegable en vez de estar siempre a la vista, y si la factura no lleva retención
    no aparece ningún número falso.
  - **Las cantidades se ven con coma, no con punto** (123,45 en vez de 123.45), como se escriben en
    España.
  - **El aviso rojo "No leído" ya no confunde**: si la IA propone un número pero no está segura,
    ahora dice "Dudoso, revisar" (hay un dato, compruébalo); "No leído" se reserva para cuando de
    verdad no hay nada que mostrar.

  Auditoría final (revisión cruzada por tres ángulos distintos, como en toda tarea de este tamaño):
  se encontró y corrigió un fallo real antes de cerrar la tarea — al convertir una coma en un punto
  para mandar el importe al servidor, un error de tecleo con una coma de miles (escribir "1,234"
  queriendo decir 1234) se habría convertido en silencio en un importe casi 1000 veces distinto, sin
  ningún aviso. Corregido para que ese caso ambiguo se rechace con un error claro en vez de
  aceptarse mal.

- **La pantalla de confirmar, reorganizada en bloques** (08/08/2026): tras el rediseño de arriba,
  Julio pidió agrupar visiblemente los datos por tipo en vez de tenerlos todos sueltos: los datos
  de la contraparte (proveedor/cliente) por un lado, los importes por otro, la fecha y el número de
  factura en su propio bloque, y los datos de la propia empresa (que no lee la IA, vienen del
  registro) al final, tal cual estaban.

- **Las cantidades con coma se colaron solo a medias** (08/08/2026): el cambio de "punto a coma" de
  arriba solo se había hecho en la pantalla de confirmar una factura nueva; el panel de facturas ya
  guardadas, la ventana de editar tramos de IVA y el historial seguían mostrando el punto de
  siempre. Julio lo señaló explícitamente ("esto ya te lo comenté que lo cambiaras, no puede volver
  a pasar"). Corregido de raíz: ahora las 4 pantallas comparten una única pieza de código para
  mostrar/editar importes, así que un fallo así no puede volver a colarse en una pantalla sí y en
  otra no.

- **Check verde de "CIF verificado" + explicación de por qué no se puede confirmar** (08/08/2026):
  antes, cuando el CIF de la contraparte quedaba verificado, aparecía un texto largo "CIF de
  contraparte verificado". Julio pidió algo más discreto: un check verde al lado del dato, mismo
  estilo que el aviso rojo de "dudoso, revisar". También se añadió un aviso claro explicando POR QUÉ
  a veces el botón "Confirmar y guardar" no deja avanzar: cuando el CIF de la propia empresa no
  aparece en la factura, solo un administrador de la asesoría puede confirmarla así (regla de
  responsabilidad ya existente, ahora explicada en pantalla en vez de solo bloquear en silencio).

- **S6.2 — Laboratorio OCR, una herramienta de diagnóstico solo para Julio** (08/08/2026): petición
  directa de Julio para poder ver, factura a factura, "las 3 fotografías" de cómo se procesó un dato
  a lo largo de todo el camino: qué leyó la IA en crudo, qué calculó el programa después de aplicar
  sus reglas internas, y qué quedó finalmente guardado tras los cambios del empleado. Así puede
  averiguar si un dato salió mal porque la IA leyó mal, porque el cálculo interno descartó algo
  bueno, o porque fue una corrección legítima de una persona — y con el tiempo, mejorar la
  precisión del sistema. También incluye, aparte, una comparativa de qué leyó cada uno de los 6
  motores de IA candidatos en esa factura (cuando esa comparativa estuviera encendida).

  Julio pidió inicialmente que se pudiera abrir desde la propia pantalla de facturas de cada
  asesoría, pero al aprobar la spec técnica lo corrigió: **el laboratorio solo puede verlo él
  mismo, nunca ninguna asesoría desde su panel normal de facturas** ("cada uno el suyo"). Por eso
  vive en una pantalla nueva, propia del panel de plataforma (el mismo sitio que ya tenía el
  interruptor de S4.10 y el ranking de modelos de S4.8), donde Julio elige primero QUÉ asesoría
  quiere mirar, ve su lista de facturas ya confirmadas, y desde ahí abre "Ver" (la foto) o
  "Laboratorio" (las 3 lecturas) de cualquiera. El panel de facturas de cada asesoría se comprobó
  con una prueba automática dedicada que no gana absolutamente nada nuevo con esta tarea.

  Auditoría (tres ángulos distintos): se encontró y corrigió un fallo real antes de cerrar la
  tarea — el listado de facturas del laboratorio reutilizaba por error la misma pieza que ya usa el
  panel normal para "una página de 50 en 50", así que una asesoría con más de 50 facturas
  confirmadas se habría quedado sin ver las más antiguas, sin ningún aviso de que faltaban. Se
  corrigió para que el laboratorio muestre siempre la lista completa. También se aprovechó para
  mostrar los tramos de IVA (antes se quedaban invisibles sin querer en las 3 lecturas) y para que
  los tipos de datos del laboratorio reutilicen los ya existentes del resto de la aplicación en vez
  de duplicarlos.

- **Julio activa de verdad la comparativa de 6 IAs + reprocesa las facturas antiguas** (09/08/2026):
  tras usar el laboratorio por primera vez, Julio encendió el interruptor real desde
  "Plataforma → Ajustes" — a partir de ese momento, cada factura nueva que se sube dispara de
  verdad las 6 lecturas de IA (gasto real recurrente, decisión suya). También pidió reprocesar las
  29 facturas que ya tenía Setex, para que también tuvieran su comparativa. Al hacerlo salieron dos
  problemas reales, los dos resueltos en el momento: (1) el primer intento se lanzó sin querer
  desde la pieza del sistema equivocada, así que 3 de los 6 modelos de IA (los dos "Gemini" y
  "Claude") fallaron en las 7 facturas que sí cumplían los requisitos para reprocesarse — se
  relanzó solo esos 3, sin repetir (ni volver a pagar) los otros 3 que ya habían salido bien; (2)
  "Claude" sigue sin poder leer esas facturas por un límite de uso de la cuenta de Google Cloud de
  Julio (no un fallo del programa) — hace falta que Julio pida ampliar ese límite desde la propia
  consola de Google para que se resuelva solo. Resultado: 35 de las 42 lecturas posibles (5 de los
  6 modelos, en las 7 facturas) ya están guardadas y visibles en el laboratorio. De paso, Julio
  perdió el acceso a su propia cuenta y se usó por primera vez la herramienta ya construida para
  resetear una contraseña sin que nadie más la vea ni la fije por él.

- **El laboratorio se abre en una ventana emergente + "Ver ejemplos" en el Ranking OCR**
  (09/08/2026): dos ajustes que Julio pidió nada más empezar a usar las pantallas nuevas. (1) Las 3
  lecturas del laboratorio ya no aparecen pegadas debajo de la tabla de facturas: se abren en una
  ventana flotante encima, como el resto de ventanas de la aplicación. (2) La pantalla "Ranking
  OCR" (que compara qué tal lee cada uno de los 6 modelos de IA) solo mostraba números resumidos;
  ahora cada motor tiene un botón "Ver ejemplos" que abre una ventana con hasta 5 facturas reales
  que ese motor leyó, no solo la nota media.

  Al construir esto, la revisión de calidad encontró un problema real de privacidad **antes de
  publicarlo**: esa ventana de "ejemplos" iba a enseñar, sin querer, el CIF y el nombre reales de
  clientes de cualquier asesoría (no solo la de Julio) a quien tuviera el permiso de super-admin —
  un dato identificable de una empresa real, visible con solo un clic. Se corrigió ocultando esos
  dos datos concretos de esa ventana (el resto, importes y fechas, se sigue viendo igual); el resto
  del dato ya guardado en la base de datos no se ha tocado, sigue pendiente la misma decisión de
  fondo sobre si cifrarlo que ya se había dejado anotada para más adelante.

- **El laboratorio pasa a panel lateral + el panel de Empresas, mucho más compacto** (09/08/2026):
  dos correcciones más de Julio tras seguir usando las pantallas. (1) La ventana flotante del
  laboratorio de hace un momento se sustituye por un panel que sale por el lado derecho de la
  pantalla, en vez de aparecer centrado — más cómodo para consultarlo mientras se ve el resto.
  (2) El panel "Empresas" tenía 4 enlaces en cada fila (Editar, Ver facturas, Historial, Borrar)
  que la hacían más ancha de lo necesario. Ahora cada fila solo tiene "Ver facturas"; "Editar" y
  "Borrar" pasan a ser dos botones únicos junto a "Nueva empresa", arriba del todo:
  - **Editar**: activa la edición de todos los campos de todas las empresas a la vez (nombre, CIF,
    notas, estado); cada campo se guarda solo al pasar a otro, sin necesidad de un botón "Guardar"
    en cada fila.
  - **Borrar**: aparece una casilla junto a cada empresa para marcar cuáles quieres borrar; al
    darle a "Borrar seleccionadas" sale un aviso emergente listando los nombres exactos antes de
    confirmar, y borra todas las marcadas de una vez.
  - El historial de cambios por empresa se retira por ahora (decisión de Julio).
  - Las columnas de la tabla ahora se pueden ensanchar o estrechar arrastrando el borde, como en
    Excel; empiezan más estrechas que antes (la de "Notas", muy estrecha) y el ajuste que hagas se
    recuerda la próxima vez que entres desde el mismo ordenador.

- **Ordenar las tablas pulsando la cabecera + columnas del panel de Facturas también
  redimensionables (10/08/2026)**: Julio pidió, en las dos tablas grandes de la aplicación
  ("Empresas" y "Facturas"), poder mover el ancho de las columnas sin tener que pulsar "Editar"
  antes (ya funcionaba así en "Empresas", pero el asa para agarrar era pequeña y difícil de
  encontrar — se ensanchó y se le puso un fondo tenue permanente para que se vea sin pasar el
  ratón por encima) y, sobre todo, poder ordenar las filas pulsando el nombre de la columna que
  quisiera, como en un Excel de verdad. Ahora las dos tablas funcionan así: un clic ordena de menor
  a mayor (o alfabéticamente), otro clic lo invierte, y un tercer clic vuelve al orden normal (más
  reciente primero). El panel de "Facturas" no tenía NINGÚN redimensionado de columnas hasta ahora
  (solo lo tenía "Empresas"); se añadió igual, junto con el orden. Antes del cambio se comprobó que
  el aviso de Julio de que "no veía los últimos cambios" no era un fallo de este proyecto sino de
  la aplicación instalada en su móvil/navegador, que guarda una copia local y tarda en darse cuenta
  de que hay una versión nueva (recargar la página dos veces, o cerrar y reabrir la app instalada,
  lo soluciona).

- **El arrastre de columnas no funcionaba de verdad en el móvil (10/08/2026)**: Julio insistió en
  que seguía sin poder mover las columnas "fácilmente sin entrar en Editar" después del cambio de
  arriba. En vez de suponer, se probó la aplicación real con un simulador de pantalla táctil (como
  si fuera un dedo tocando un móvil, no un ratón) — y ahí apareció el fallo de verdad: el código
  solo sabía escuchar al ratón (agarrar, mover, soltar), y un móvil o una tablet no usan ratón, así
  que el arrastre con el dedo no hacía absolutamente nada, por muy grande que fuera el asa. Se
  añadió el mismo mecanismo pero para gestos con el dedo, se comprobó de nuevo con el mismo
  simulador táctil sobre la aplicación ya desplegada (antes: 160px se quedaban en 160px; después:
  160px pasan a 220px al arrastrar) y se confirmó que ya funciona en las dos tablas.

- **Todas las tablas de la aplicación, mucho más parecidas a un Excel de verdad (10/08/2026)**:
  Julio, tras probar el arreglo del punto anterior, dijo que en su ordenador seguía sin poder
  mover las columnas sin pulsar "Editar" primero, y pidió algo más ambicioso: que TODAS las tablas
  de TODAS las pantallas de la aplicación (no solo Empresas y Facturas) fueran así de
  interactivas. En vez de seguir arreglando el mecanismo casero a mano, se cambió por una pieza ya
  hecha y probada por miles de aplicaciones (una "librería" llamada TanStack Table): mueve columnas
  y ordena por cabecera igual que antes, pero de forma más sólida, porque el propio fabricante ya
  se ha encargado de que funcione bien con ratón y con dedo a la vez, en vez de tener que
  mantenerlo nosotros a mano. Se aplicó a las 9 tablas que tiene la aplicación entera: las dos ya
  conocidas (Empresas, Facturas) y siete más que hasta ahora no se podían ni ordenar ni
  redimensionar (la lista de asesorías y sus estadísticas en el panel de plataforma, los registros
  pendientes de aprobación, el ranking de comparación de las IAs, y las tres tablas del
  laboratorio de diagnóstico).

  Al construirlo salió un fallo real y curioso, de los que rara vez se ven: un mismo gesto de
  arrastre con el dedo funcionaba bien la primera vez que se abría la pantalla en una sesión, pero
  no la segunda. Investigando a fondo (no se asumió que era "cosa del test") se encontró que el
  motivo era una sutileza de cómo React (la tecnología con la que está hecha toda la pantalla)
  decide en qué orden aplica dos cambios de estado seguidos cuando viven en dos sitios distintos —
  no siempre en el orden en que se pidieron. Se corrigió juntando esos dos cambios en un único
  sitio, forzando el orden correcto siempre. Comprobado dos veces contra la aplicación real ya
  desplegada, con ratón en un ordenador y con un dedo en un móvil simulado, antes y después de este
  segundo arreglo.

- **Encontrado el motivo de verdad de "sigo sin poder mover columnas" (10/08/2026)**: Julio insistió
  una tercera vez en que en su ordenador (con Chrome, ya descartado que fuera la caché del
  navegador probando en una ventana de incógnito) seguía sin funcionar, y dio un dato clave: "el
  cursor cambia pero no se mueve". Con esa pista se probó con datos de verdad — un nombre de
  empresa largo, no los nombres cortos usados en todas las pruebas anteriores — y ahí apareció el
  fallo real: cuando una celda tiene un texto largo, el navegador estaba **ignorando por completo**
  el ancho de columna que la aplicación le pedía, sin avisar de ello. Con un nombre corto esto
  nunca se notaba, por eso ni las pruebas automáticas ni las primeras comprobaciones lo habían
  visto. Esto explicaba también otra cosa que Julio había notado: por qué las columnas se veían
  "más juntas" al activar "Editar" (con Editar, cada celda pasa a ser una casilla de escribir, que
  no sufre este problema del navegador).

  Corregido dándole a la tabla, además de las anchuras de cada columna, un ancho TOTAL — la suma de
  todas — algo que el navegador necesita para respetar de verdad lo que se le pide en vez de
  decidir por su cuenta. Se aplicó a las 9 tablas de la aplicación, junto con recortar con puntos
  suspensivos ("…") el texto que no cabe, en vez de dejarlo desbordarse sin control. Comprobado con
  los mismos nombres largos que causaban el fallo, contra la aplicación real ya desplegada: ahora
  la columna mide exactamente lo que debe medir y el arrastre funciona de principio a fin.

- **La empresa con la factura más reciente, siempre arriba + buscar empresa escribiendo
  (10/08/2026)**: dos peticiones nuevas de Julio, para todas las asesorías por igual. (1) La
  pantalla "Empresas" ahora empieza siempre ordenada con la empresa que subió la última factura
  arriba del todo, sin tener que pulsar nada — las que nunca han subido ninguna van al final, sin
  que importe el orden entre ellas. Sigue pudiéndose cambiar pulsando cualquier otra cabecera,
  como siempre. (2) En el panel de "Facturas", el desplegable para filtrar por empresa (que
  obligaba a abrir la lista entera y buscar con la vista) pasa a ser un campo de texto: se escribe
  el nombre (o parte de él) y la lista se va acortando sola, sin distinguir mayúsculas de
  minúsculas — mucho más rápido cuando hay muchas empresas dadas de alta.

- **S6.6 — el Laboratorio dice claramente dónde falló la IA, no solo qué se corrigió (11/08/2026)**:
  Julio entregó un documento de otra aplicación suya como referencia y pidió adaptar su idea al
  Laboratorio de diagnóstico (la pantalla, solo para los "tech" de plataforma, que compara cómo se
  leyó cada factura). Antes, para saber "¿en qué campo se equivocó el sistema?" había que leer una
  lista de diferencias aparte, y esa lista solo aparecía si algo había cambiado. Ahora hay una única
  tabla, siempre visible, con TODOS los datos de la factura (CIF y nombre del proveedor, número de
  factura, fecha, base, IVA, total, y los tramos de IVA aparte) y, para cada uno, dos columnas —
  "qué decidió el sistema" antes de guardar y "qué se confirmó" — más un aviso de un vistazo: un
  visto verde si coinciden, una cruz roja si no, o un guion gris cuando no hay nada con qué
  comparar (por ejemplo, un número de factura que nunca llegó a leerse). Si no hubo ningún cambio,
  la tabla entera sale en verde, en vez de mostrar antes un aviso aparte de "sin correcciones".

  La parte más delicada, encontrada pensando en los casos raros ANTES de programar (como manda la
  regla del proyecto): "qué decidió el sistema" no puede sacarse simplemente del dato que hay HOY
  guardado, porque una factura ya confirmada se puede editar más adelante (por ejemplo, semanas
  después, si alguien se da cuenta de un error). Si se hubiera sacado de ahí, un campo editado
  mucho después habría aparecido en VERDE, como si el sistema lo hubiera leído bien desde el
  principio — una mentira sutil pero real. Se corrigió reconstruyendo siempre esa columna a partir
  de la primera lectura de la IA (que nunca cambia), no del dato actual. Julio aprobó este arreglo
  al presentárselo antes de escribir el primer test, tal y como pide el proceso del proyecto.

  Por dentro, se creó también una única "función árbitro" reutilizable (¿coinciden dos importes?,
  ¿dos fechas?, ¿dos CIF?, ¿dos nombres?) que antes vivía duplicada sin que nadie se hubiera dado
  cuenta: una copia se usaba solo para calcular qué corregir al confirmar una factura, y el
  Laboratorio iba a necesitar la misma lógica para pintar los avisos verdes/rojos. A partir de
  ahora hay un solo sitio que decide "esto es lo mismo o no", reutilizado en los dos lugares — así,
  si algún día se afina ese criterio, se afina en un único sitio, no en dos que podrían acabar
  divergiendo sin que nadie se entere. Tres auditorías independientes revisaron el cambio (ninguna
  encontró fallos de seguridad ni de aislamiento entre asesorías); sí encontraron y se corrigieron
   varios detalles de limpieza de código (por ejemplo, dos trozos de lógica casi idénticos para
   comparar tramos de IVA que se unificaron en uno solo). 795 pruebas automáticas del backend y 296
   del frontend, todas en verde.

- **S6.7 — banco de pruebas real para elegir la mejor IA y la mejor imagen (12/08/2026)**: se
  construyó un laboratorio que prueba cada factura ya confirmada con las 3 maneras de preparar su
  imagen (original, realce normal y realce local CLAHE) y con los 6 lectores de IA. Son 18 pruebas
  por factura. Cada lectura se compara contra los datos que una persona dejó confirmados, así que el
  ranking ya no mide si una IA parece coherente consigo misma, sino si acertó de verdad el CIF, el
  nombre, el número, la fecha, los importes y los tramos de IVA.

  El panel técnico permite ver qué combinación gana en cada grupo de datos, el detalle de todas las
  combinaciones, y lanzar un lote limitado de las últimas facturas. Enseña el avance aunque se
  recargue la página y no permite que dos personas disparen dos lotes caros a la vez. Un fallo de un
  lector o de una factura no bloquea a los demás ni deja el avance congelado.

  También se cerró una protección pendiente desde tareas anteriores: los CIF y nombres de proveedor
  que guardaban los experimentos antiguos ya no quedan legibles dentro de los resultados de prueba.
  Se cifran con una llave distinta para cada asesoría, igual que las facturas reales. La migración
  transforma el histórico existente sin perderlo. El Laboratorio usa el benchmark real por campo y
  el ranking general de ejemplos no devuelve nunca esos datos. Se verificó el cifrado nuevo, la
   migración desde el esquema viejo y el Laboratorio con PostgreSQL real.

  Antes de cerrar se revisaron situaciones de concurrencia, es decir, cuando dos acciones ocurren
  casi a la vez. Ahora el lote guarda su lista cerrada de facturas desde el instante en que se pulsa
  el botón, no una lista que pueda cambiar mientras espera al worker. Dos clics simultáneos solo
  crean un lote. También se quitó el lector de ranking antiguo del camino automático, para no pagar
  dos experimentos distintos sobre la misma factura, y si falta la configuración de un lector queda
  anotado como fallo sin repetir eternamente los que sí están disponibles.

- **Refuerzo de seguridad y fiabilidad del banco de pruebas S6.7 (12/08/2026)**: antes de lanzar
  dinero real, se corrigieron los bloqueos detectados en una segunda revisión. El lector normal de
  facturas ya no dispara el ranking antiguo por detrás: ese ranking queda guardado como historial,
  pero el banco nuevo solo se ejecuta al confirmar una factura, cuando existe una respuesta humana
  con la que compararlo. Si falta la configuración de una de las seis IAs, no desaparece de la
  comparación: queda anotada como "no disponible", sin llamar a Internet ni inventar un resultado.

  El botón del lote ahora guarda una lista exacta de las facturas que eligió en ese instante y la
  entrega al trabajador después de que la base de datos haya confirmado el cambio. Dos clics a la
  vez no pueden crear dos listas caras: la propia base de datos deja pasar solo una. Si falla la
  cola que avisa al trabajador, el panel muestra el lote como fallido en vez de fingir que sigue en
  marcha para siempre. Los errores técnicos de una IA se guardan con una etiqueta segura, sin copiar
  posibles respuestas, instrucciones o secretos del proveedor. También se incluyeron los seis datos
  cifrados de los experimentos antiguos en el cambio periódico de llaves. Todo se comprobó contra
   Postgres y Redis reales, además de los controles automáticos de estilo y tipos.

- **Primera ejecución real del banco de pruebas en Setex (12/08/2026):** Julio autorizó probar las
  29 facturas ya confirmadas de Setex. Se hicieron las 18 pruebas previstas por factura y se guardó
  el resultado de cada una: **522 resultados en total**. Cinco lectores respondieron sus 87 intentos
  cada uno. Claude no tenía cuota disponible en Google y sus 87 intentos quedaron guardados
  honestamente como "no pudo leer", no se rellenaron con resultados de otro lector ni se inventaron.

  En esta primera muestra, Gemini Flash con la imagen realzada fue el mejor resultado global: acertó
  175 de 191 datos que se podían comparar (91,62%). No significa todavía que vaya a ganar siempre:
  por ejemplo, Azure acertó todas las fechas de esta muestra y Gemini Flash/Pro todos los tramos de
  IVA que sí tenían un tramo confirmado. Ninguna de esas 29 facturas tenía número de factura
  confirmado, por lo que todavía no hay una comparación honesta para ese dato. Todo se puede ver en
  el menú técnico, en **Ranking OCR**, y al abrir una factura en el Laboratorio.

## 5. Qué queda por delante

- **Sprint 3 completo** (S3.1-S3.5 cerrados 23/07/2026). Queda pendiente el frontend de la edición de
  facturas (S3.3 solo trajo la capacidad de corregir con seguridad, no la pantalla para hacerlo cómodo),
  si hace falta más adelante.
- **Sprint 4 COMPLETO** (S4.1-S4.7 cerrados 24/07/2026 — panel de plataforma + white-label + PWA
  multi-tenant). S4.6 se cerró con alcance acotado (ver entrada de arriba): el caso de subdominios
  nuestros (`panel-staging.autoken.es`) ya tiene certificado real de verdad desde el 27/07/2026 (ver
  entrada de arriba); sigue pendiente el caso de un dominio propio de una gestoría cliente
  (`setex-facturas.autoken.es` sigue reservado para esa prueba concreta), que es un mecanismo más
  complejo (el dominio no se conoce de antemano).
- **Sprint 2 COMPLETO** con el cierre de S2.2 (24/07/2026) — verificación en dispositivo real
  pendiente (ver entrada de arriba), igual que la infra de S4.6.
- **Lote de cierre de backlog previo al Sprint 5 — COMPLETO** (decidido con Julio el 24/07/2026):
  las 5 tareas (S4.9 app-shell, S2.2 captura guiada, S4.10 interruptor admin-tech, S2.9/S2.10
  realce+comparativa, S4.8 ranking multi-modelo) cerradas y mergeadas el 25/07/2026.
- **Sprint 5 (hardening+QA) COMPLETO DEL TODO, incluida la infraestructura real** (25-27/07/2026,
  orden acordado con Julio): las 6 tareas — S5.1 (cabeceras y límites), S5.6 (monitorización y
  alertas), S5.2 (cifrado por tenant), S5.4 (pentest propio), S5.5 (pruebas de carga) y S5.3
  (backups + restore drill) — cerradas y mergeadas. El stack de monitorización de S5.6 y los
  backups nocturnos reales de S5.3 ya están funcionando de verdad, no solo construidos (ver
  entradas de arriba) — la copia de seguridad ya se sube cada noche a una VPS distinta, y se
  comprobó de verdad que un backup real se puede restaurar. Solo queda una cosa menor sin usar
  nunca en producción (no hace falta salvo sospecha de filtración): el script de rotación de la
  clave de cifrado de S5.2.
- **Fase de despliegue**: el día que Setex (la v1 actual) se apaga y todo el mundo pasa a usar esta versión
  nueva.

**Avance estimado hacia producción a día de hoy: ≈83%** (43 de 53 tareas del plan "core" completas
del todo — S4.9 es una tarea nueva, no estaba en el recuento original de 51, añadida para cerrar el
hueco de integración detectado el 23/07/2026 — sin contar el módulo de Verifactu ni la limpieza
final del servidor viejo, que van en paralelo y no bloquean el lanzamiento). **Sprint 2, Sprint 3,
Sprint 4 y Sprint 5 completos. Lote de cierre de backlog previo al Sprint 5 COMPLETO. Siguiente: la
Fase de Despliegue (go-live y migración de Setex) — ver PLAN MAESTRO.**

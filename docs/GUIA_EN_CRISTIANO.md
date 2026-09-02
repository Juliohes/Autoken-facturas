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

- **Laboratorio más cómodo y cámara más fiable (13/08/2026):** el Laboratorio técnico ya no abre una
  ventanita estrecha para estudiar una factura. Ahora se abre como una pantalla completa, con un botón
  claro para volver al resumen sin perder la asesoría que se estaba mirando. Dentro se puede cambiar entre
  la foto original, lo que leyó la IA, lo que decidió el sistema, lo que acabó confirmando la persona y la
   comparación entre IAs.

- **R-032 — comparación justa del OCR (22/08/2026):** cada resultado del banco guarda la versión del
  contrato, la versión de normalización, un identificador del documento y de la verdad confirmada,
  el número de páginas y las mismas variantes. Así se puede comprobar que dos motores fueron medidos
  sobre exactamente la misma entrada. El benchmark R-032 separa cuatro candidatos mínimos: Gemini 3.5
  Flash, Gemini 3.6 Flash, Gemini 3.5 Flash-Lite y Mistral OCR 4 con anotación estructurada.

  Además de aciertos por campo y por campo crítico, el informe muestra si todos los críticos acertaron,
  los tramos de IVA, el cuadre aritmético, posibles valores sin verdad de referencia, errores y tiempos
  p50/p95. El coste de API y las correcciones manuales quedan vacíos cuando no existe telemetría real,
  en lugar de inventar un cero. El benchmark sigue siendo un informe para revisión técnica: nunca
  cambia automáticamente el motor de producción.

  Arriba del Laboratorio hay también un resumen de verdad: enseña qué combinación de lector e imagen ha
  acertado más para cada tipo de dato y permite filtrar, por ejemplo, solo CIF o solo importes. Si todavía
  no existe una respuesta humana con la que comparar, dice "sin datos comparables" en vez de pintar un
  engañoso 0%. Si una IA falló porque no tenía cuota, se ve ese fallo tal cual, sin esconderlo ni rellenarlo
  con otra IA. Consultar esta pantalla no vuelve a leer facturas ni genera gasto: solo muestra resultados
   que ya estaban guardados.

- **R-033 — política OCR de producción (22/08/2026):** la IA que lee facturas en producción ya no se
  decide mirando directamente una variable de configuración ni reutilizando la lista de candidatos
  del laboratorio. Existe una política guardada en la base de datos con versión, motor, modelo,
  fallback y modo de consenso. Solo `admin-tech` puede cambiarla y cada cambio debe aumentar la
  versión. El trabajador consulta esa política y construye exactamente el primario indicado.

- **R-034 — fallback OCR condicional (22/08/2026):** el sistema no consulta dos IAs por cada factura.
  Solo usa el segundo motor si el primero falla, tarda demasiado, deja un dato crítico ausente o
  poco fiable, encuentra un CIF inválido o no consigue cuadrar los importes. Una confianza media
  únicamente en el nombre del proveedor no basta para pagar otra lectura. Si el segundo motor
  coincide, se reconcilian las lecturas; si discrepa en un dato, la factura queda para revisión y no
  se llama automáticamente a un tercer motor.

- **R-035 — consenso por campo (22/08/2026):** cuando existen dos lecturas, Autofactu ya no tiene que
  elegir una factura completa. Compara cada fecha, importe, número, CIF, tramo de IVA y demás dato con
  una normalización conservadora: por ejemplo, `121,00` y `121.00` representan el mismo importe, pero
  no se borran indiscriminadamente los guiones o barras del número de factura. Cada decisión guarda si
  fue aceptada, quedó dudosa o entró en conflicto, junto con sus fuentes y motivos. Esa explicación se
  conserva en el resultado técnico y permite revisar por qué se eligió un valor sin perder la lectura
  original.

- **R-036 — confianza del sistema (22/08/2026):** la etiqueta que declara una IA y la confianza que
  calcula Autofactu son ahora conceptos separados. El sistema parte de reglas sencillas y visibles:
  premia una lectura fuerte, el acuerdo entre motores y las validaciones correctas; limita la confianza
  cuando falla un CIF o el cuadre de importes, y resta por conflictos. El resultado guarda la puntuación
  y motivos como `engines_agree`, `invoice_math_ok` o `tax_id_checksum_failed`, mientras conserva las
  etiquetas antiguas para que las pantallas existentes sigan funcionando.

- **R-037 — diagnóstico fiscal detallado (22/08/2026):** el cuadre ya puede explicar cada tramo de
  IVA: cuota esperada, cuota leída, diferencia y si es válido, además del total general. El resultado
  antiguo `CheckResult` sigue disponible para los consumidores que solo necesitan verdadero/falso.
  Si aparece un tipo de IVA numérico que no está en la política estándar, se conserva en vez de
  borrarlo o confundirlo con IRPF, y la factura se envía a revisión. La lista de tipos conocidos vive
  separada del parser para poder cambiar la política fiscal sin reescribir la lectura OCR.

- **R-038 — aprendizaje por proveedor (22/08/2026):** tras confirmar una factura, Autofactu guarda
  únicamente patrones y contadores agregados para ese proveedor dentro de esa empresa y asesoría:
  forma del número, tipos de IVA vistos, número de tramos y campos que el humano corrigió. No guarda
  el CIF en claro ni copia facturas anteriores. El índice que encuentra el perfil es ciego y depende
  del tenant y de la empresa. Durante las primeras tres confirmaciones el perfil está en arranque y
  no puede influir en decisiones automáticas. Cuando ya está maduro, el lector puede usarlo como una
  señal débil para detectar una anomalía o pedir fallback, pero nunca sustituye lo que dice claramente
  la factura.

- **R-039 — evidencia local opcional (22/08/2026):** existe un comprobador experimental para
  Tesseract que puede buscar CIF, número, fecha e importe en el texto de una imagen. Si encuentra un
  dato suma una señal; si no lo encuentra no invalida la lectura de la IA. Si Tesseract no está
  instalado o tarda demasiado, la evidencia queda indeterminada. Este módulo no se ejecuta dentro del
  camino crítico de subida, por lo que no añade varios segundos a la experiencia de usuario.

- **R-043 — colas separadas (22/08/2026):** la lectura que desbloquea al usuario va a una cola
  primaria independiente. Comparativas, benchmarks y mantenimiento van a una cola de fondo y tienen
  su propia configuración de worker. Así un lote de laboratorio no puede ocupar todos los huecos y
  retrasar la lectura de una factura recién subida.

- **R-040 — experimento offline de imagen (22/08/2026):** el laboratorio puede generar cinco
  versiones de la misma foto: original, natural, CLAHE, escala de grises y Sauvola. El informe usa
  exactamente la misma verdad confirmada para todas, de modo que la comparación no confunde una
  mejora de imagen con una diferencia de factura. Es un proceso offline y no cambia el preprocesado
  de producción por sí solo.

- **R-041/R-042 — challengers de layout (22/08/2026):** se ha definido una puerta común para
  experimentos con PaddleOCR y Surya. Esa puerta devuelve señales sobre tablas, tramos de IVA y
  orden de lectura, pero no decide importes ni sustituye al OCR principal. Los motores pesados
  seguirán viviendo en servicios separados de laboratorio, no dentro del contenedor de la API.

- **R-044/R-045 — límites y circuito de proveedor (22/08/2026):** el worker de usuario tiene un
  máximo inicial de cuatro trabajos y el de fondo uno. Además, cada combinación de motor y modelo
  tiene una máquina que puede cerrarle temporalmente el paso tras varios fallos, esperar y permitir
  una única prueba. Esto evita que una caída del proveedor provoque cien llamadas de fallback a la
  vez. La máquina conserva su estado en Redis y el worker la consulta antes de llamar al primario;
  si Redis falla, no bloquea la lectura principal.

   También se reforzó la cámara al subir una factura desde el móvil. La app intenta usar primero la cámara
  trasera, pero si el teléfono o el ordenador solo tiene otra cámara, la acepta en vez de bloquear al
  usuario. El botón de hacer foto espera a que haya una imagen real lista, para no fallar si se pulsa muy
  rápido. Si la cámara falla o se deniega el permiso, sigue estando el botón para subir un archivo y aparece
  una opción para reintentar. Antes de pedir otra cámara se cierra la anterior, para que no queden dos
  cámaras encendidas a la vez. Las comprobaciones automáticas están en verde; aún falta probarlo con un
  Android y un iPhone reales, porque un servidor no puede imitar de verdad los permisos y cámaras físicas.
  Pasaron las 314 comprobaciones automáticas de la parte visual y de comportamiento de la aplicación antes de
  dejar el cambio listo para revisión.

   Una revisión posterior encontró tres casos límite que podían dejar la experiencia incompleta y se
   corrigieron antes de integrar: si el navegador se queda esperando una cámara sin responder, a los diez
   segundos ya ofrece reintentar; si concede la cámara pero nunca entrega imagen, también aparece ese
   reintento; y la tabla ancha que compara IAs se puede desplazar lateralmente en móvil para que ninguna
   columna quede escondida. Ahora son 316 comprobaciones automáticas del frontend en verde. Solo falta probar
   estos gestos y permisos con un Android y un iPhone físicos.

- **Arreglo urgente al subir fotos (13/08/2026):** una foto hecha desde el móvil no fallaba por la cámara;
  llegaba correctamente al servidor, pero el antivirus que debe revisarla antes de guardarla se había parado.
  La aplicación hizo lo correcto: rechazó la subida en lugar de almacenar un archivo sin revisar. Se reinició
   el antivirus y se comprobó desde la propia aplicación que vuelve a analizar archivos. Además, ahora si ese
   proceso se cae de nuevo el servidor lo detecta y lo reinicia solo tras varias comprobaciones fallidas.

- **Fotos manuales y comprobación de CIF sin bloqueos falsos (13/08/2026):** la aplicación ya no hace fotos
  por su cuenta. La persona entra, pulsa "Abrir cámara" y ve la cámara ocupando toda la pantalla, con un marco
  grande y vertical como una hoja para acercar bien la factura. Solo al pulsar "Tomar foto" se guarda esa
  imagen para revisarla. Al cerrar, repetir o elegir un archivo, la cámara se apaga de verdad para no dejar el
  piloto encendido ni mezclar dos fotos.

  La empresa ya aportó su razón social y CIF al registrarse. Ese es el número conocido que la app busca en la
  factura, no un número que la IA pueda inventar. Si no aparece, el usuario puede confirmar claramente que la
  factura es de su empresa y la asesoría verá después una marca "Revisar CIF propio" en su panel y Excel.
  Esa marca se guarda como un hecho de la confirmación, para que una relectura futura de la IA no cambie la
  historia.

  También se solucionó el bloqueo injusto al corregir un CIF de proveedor: ahora la pantalla vuelve a comprobar
  el CIF que la persona acaba de escribir y actualiza el mensaje. Aunque el navegador diga que es válido, el
  servidor lo revisa otra vez justo antes de guardar. Así se corrige el error de la IA sin abrir un agujero de
  seguridad. Pasaron las pruebas de aislamiento entre asesorías, 10 pruebas backend nuevas contra bases reales
  y las 320 pruebas del frontend. Queda probar físicamente la cámara en Android y iPhone.

- **Flujo final de hacer una foto (13/08/2026):** Julio ajustó el recorrido para que se parezca a una cámara
  normal y sea más rápido. En la pantalla de captura se elige si la factura es recibida o emitida y se pulsa
  "Tomar foto". Solo entonces se abre la cámara ocupando toda la pantalla, con un marco grande para acercar la
  factura. Dentro se pulsa "Capturar foto" y la aplicación la manda directamente a leer: no hay una pantalla
  extra para aprobar la propia foto. Mientras trabaja aparece "Procesando factura..." y después llega la
  pantalla donde se revisan los datos que entendió la IA. Subir un archivo sigue el mismo recorrido directo.

### S6.12 — Varias fotos para una sola factura e historial privado (14/08/2026)
Ahora una factura de varias páginas se puede fotografiar por partes: primero los datos fiscales, después los
importes y, si hace falta, hasta tres fotos más. La aplicación las guarda como un único expediente y la IA recibe
todas juntas, en orden, para completar una única factura. Ninguna foto extra crea otra factura ni se pierde en el
camino.

La cámara ocupa casi toda la pantalla del móvil para acercar mejor el documento. La linterna aparece solo en los
teléfonos que realmente permiten controlarla desde el navegador. Tras cada foto de una factura larga se muestran
miniaturas: se puede quitar una foto equivocada, añadir otra o enviar el conjunto cuando haya al menos dos.

El historial ahora enseña a cada empleado exactamente sus últimos 20 envíos, incluso si la IA sigue trabajando o
falló. Un compañero no puede ver ni descubrir que existe una foto ajena, aunque trabaje para la misma empresa. El
administrador de la asesoría conserva su vista completa para poder dar soporte. Antes de cerrar se comprobaron
estos límites intentando cruzarlos entre usuarios, empresas y asesorías diferentes.

### S6.13 — Una factura guardada no vuelve a parecer perdida (17/08/2026)
Una foto y la lectura de la IA son dos pasos distintos. Antes, si la IA tardaba más de un minuto, la pantalla se
rendía y parecía que la foto se había perdido aunque ya estuviera guardada. Ahora avisa claramente de que la
factura está dentro, permite cerrar la pantalla y retomarla desde el historial cuando la IA termine.

También se añadió una reserva para que dos trabajadores no lean ni cobren dos veces la misma factura, y un
recuperador que vuelve a poner en marcha una lectura si un reinicio la deja esperando. Las fotos corruptas o
demasiado grandes se rechazan antes de guardarse, y los reintentos siguen respetando que nadie pueda descubrir
ni tocar facturas ajenas.

Ya está desplegado y comprobado de verdad: el recuperador corre cada minuto sin fallos, el termómetro
(`/metrics`) publica cuántas facturas están pendientes/procesando/atascadas/fallidas, y la factura concreta
que motivó el aviso de Julio quedó confirmada como "pendiente de comprobación" (nunca perdida ni cobrada dos
veces).

### S6.14 — Fotos más nítidas y una IA que dice "estoy segura del CIF, no tanto del nombre" (18/08/2026)
Julio detectó dos cosas al usar la app: la foto no se hacía con la máxima resolución del móvil, y la IA se
equivocaba más de la cuenta en el nombre del proveedor. Las pruebas con las 29 facturas reales confirmaron
el diagnóstico: la IA acierta la fecha el 100% de las veces y los importes el 99%, pero el nombre del
proveedor solo el 59%.

¿Por qué fallaba el nombre? Porque la IA daba una única nota de confianza para "CIF + nombre" juntos, y no
podía decir "del CIF estoy segura, del nombre no tanto". Además, a veces el logo de la factura dice una
cosa ("Bar Manolo") y la razón social legal que acompaña al CIF dice otra ("Hostelería Manolo SL").

Qué se ha hecho (todo gratis, sin gastar más en IA):
- La cámara ahora pide al móvil la mayor resolución que pueda dar, y si el recorte automático del papel
  sale pequeño (porque la foto se hizo de lejos), se amplía antes de subirla.
- El detector de bordes del papel aguanta mejor sombras y esquinas imperfectas (antes, una sombra podía
  hacer que no encontrara el documento).
- La IA ahora da DOS notas de confianza separadas: una para el CIF y otra para el nombre. Ser estrictos
  con el CIF (que tiene efectos fiscales) pero flexibles con el nombre (que se corrige de un vistazo)
  evita que la app mande a revisión facturas que están bien.
- Se le dice a la IA explícitamente: "si el logo y la razón social legal difieren, quédate con la legal".
- Si una comprobación matemática detecta que un CIF o un total no cuadran, la app ya no muestra ese dato
  como "leído con confianza alta": lo baja a "dudoso" antes de enseñarlo.
- Si una foto sale tan mal que no se lee ni el proveedor, ni el total ni la fecha, la app ya no abre un
  formulario lleno de huecos vacíos: dice "la foto no se pudo leer" y devuelve directamente a la cámara
  para repetirla. En el historial esas facturas aparecen con su propia etiqueta y un enlace "Repetir
  foto".
- La app mide lo borrosa que está cada foto y, si sale movida, avisa (sin bloquear): "revisa bien los
  datos antes de confirmar".

Antes de cerrarlo, tres revisiones independientes encontraron y corrigieron un fallo que habría roto la
verificación automática de GitHub y varios comentarios del código que no contaban la verdad. Pendiente:
probarlo con móviles reales y repetir la medición de aciertos con fotos ya nítidas, para ver si el nombre
del proveedor mejora como se espera.

### IRPF separado del IVA en la lectura automática (2026-08-20)
Se corrigió un caso importante de las facturas de profesionales: una retención de IRPF, por ejemplo del 19%,
no es IVA y no debe aparecer como un tramo de IVA. La IA recibe ahora dos casillas propias para el tipo de
retención y su importe, además de sus niveles de confianza. La aplicación rechaza como tramo cualquier tipo de
IVA que no sea 21%, 10%, 4% o 0%, para no guardar una retención mezclada con el IVA por error.

Estos datos viajan desde la respuesta de la IA, pasan por el trabajador que procesa la factura y se guardan
separados en la base de datos. Al abrir la pantalla de comprobación, el importe del IRPF ya aparece rellenado en
su casilla y se resta al comprobar la cuenta de la factura: base imponible + IVA - IRPF = total. La persona puede
corregirlo antes de confirmar, y la factura definitiva conserva el importe separado del IVA.

### S6.15 — Quitar la espera muerta del OCR (latencia percibida sin tocar el motor, 2026-08-19)
Julio reportó que el tiempo que tardaba la IA en mostrar el resultado era inaceptable. Como el motor principal
(Gemini Flash) ya es rápido pero tiene un tiempo irreducible de ~15 segundos, esta iteración se centró en
**quitar las esperas muertas del sistema** sin tocar la precisión ni cambiar de modelo:

1. **Liberar al camarero (el worker)**: antes, tras terminar de leer una factura, el sistema hacía una segunda
   lectura experimental en el mismo momento, reteniendo al trabajador 15 segundos extra antes de poder atender al
   siguiente usuario. Ahora esa comparativa corre como una tarea de fondo separada; el trabajador queda libre al
   instante.
2. **Preguntar con más ganas al principio**: la pantalla de comprobación antes preguntaba "¿ya está?" cada 1,5
   segundos fijos. Ahora pregunta cada 0,5 segundos al principio (cuando es más probable que termine pronto) y
   luego se relaja a 1,5s — detecta el resultado antes y da sensación de mayor inmediatez.
3. **Descargar a la vez**: las páginas de una factura de varias hojas ahora se descargan del servidor en paralelo
   (todas a la vez) en vez de una tras otra, reduciendo la espera al de la página más lenta.
4. **Corta si se cuelga**: si un proveedor externo se queda colgado, el sistema ya no espera hasta 8 minutos
   para liberar el hueco: corta a los 2,5 minutos y marca un fallo reintentable.

Todo ello verificado con 6 tests nuevos y triple control de calidad (auditoría de 3 lentes), dejando el terreno
preparado para investigar Mistral a fondo en la siguiente fase.

### Corrección del IRPF separado del IVA (20/08/2026)

Se corrigió un problema por el que una retención, por ejemplo del 19%, podía confundirse con una línea de
IVA. Ahora la inteligencia artificial recibe instrucciones para guardar el porcentaje y el importe del IRPF
en sus propias casillas, y la pantalla de confirmación los muestra separados. El total se comprueba como:
base imponible + IVA - IRPF.

La corrección también necesitaba actualizar la estructura de la base de datos. Al probar una factura real se
descubrió que la aplicación publicada todavía usaba una versión anterior, aunque el código nuevo ya estaba
preparado. Se aplicó la migración, se reconstruyeron API, trabajador OCR y frontend, y se comprobó que el
servicio real de Setex está sano. La factura que se hubiera subido antes de ese momento conserva la lectura
antigua; las nuevas ya pasan por el circuito corregido.

### Progreso real del lector automático (R-016/R-017, 21/08/2026)

La aplicación ya guarda en la base de datos en qué etapa está trabajando el lector, separado del estado
final de la factura. Una factura recién subida queda "en cola"; después puede aparecer como preparando el
documento, leyendo, comprobando los datos, contrastando resultados o guardando el resultado.

Esto permite que la futura pantalla de progreso enseñe hechos reales y no una animación inventada. También
se guardan la hora de inicio y de final del OCR. Cada cambio lleva una marca temporal del trabajador que
tiene el documento reservado: si un trabajador antiguo despierta tarde, la base de datos rechaza su
actualización y no puede falsear el progreso de otro trabajador.

La pantalla de comprobación ya consulta una puerta pequeña de estado para mostrar ese progreso. No recibe
el CIF, la imagen, el texto bruto de la IA ni la dirección interna del almacén. Si el servidor es antiguo y
 no conoce todavía la etapa, muestra una barra indeterminada en vez de inventar un porcentaje.

### Bandeja privada de mis facturas (R-020, 21/08/2026)

Ya existe la pantalla **Mis facturas** (`/mis-facturas`). Enseña únicamente los documentos que ha subido la
persona que ha iniciado sesión, incluso si esa persona es administradora de la asesoría. La lista solo muestra
información operativa: estado, etapa del lector, fecha, dirección y número de páginas. No muestra CIF, proveedor,
número de factura, importes ni el texto bruto de la IA.

La pantalla también enseña un resumen de cuántas facturas están procesándose, cuántas están listas y cuántas
necesitan atención. Mientras haya trabajo en curso hace una sola consulta conjunta cada dos segundos, no una
consulta independiente por cada factura. Si hay muchas, se pueden cargar más usando un cursor estable para no
repetir ni saltar documentos.

### Borrador seguro mientras se revisa una factura (R-021/R-022, 21/08/2026)

La pantalla de revisión ya guarda automáticamente lo que la persona está editando, sin convertirlo todavía
en una factura definitiva. El guardado espera 750 milisegundos desde el último cambio para no mandar una
petición por cada tecla. Si dos pestañas intentan guardar a la vez, cada borrador lleva un número de revisión:
la segunda versión solo se acepta si sigue editando la versión que conocía, y una versión antigua recibe un
aviso de conflicto en vez de borrar los cambios nuevos.

Los CIF y nombres del borrador se guardan cifrados, igual que los de las facturas definitivas, y el borrador
tiene sus propias reglas de aislamiento por asesoría. Confirmar una factura espera primero a que el borrador
termine de guardarse; así no se confirma una versión distinta de la que la persona acaba de ver.

### La revisión recupera el borrador correcto (R-023, 21/08/2026)

Al volver a abrir una factura, la aplicación ya no enseña por accidente la lectura antigua de la IA si
había cambios guardados. Primero busca el borrador; si existe, muestra esos datos y conserva las marcas de
confianza que produjo la IA para que la persona sepa qué datos eran dudosos originalmente. Si nunca hubo
borrador, sigue mostrando la lectura OCR como antes.

La respuesta también indica si los datos vienen del OCR o del borrador, qué número de revisión tienen, cuándo
se guardaron y cuántas páginas tiene el documento. Así la pantalla y el servidor hablan de la misma versión.

### Confirmación atómica desde el borrador (R-024, 21/08/2026)

Al confirmar, el servidor vuelve a comprobar los datos y usa el borrador guardado como fuente de verdad,
aunque el navegador mande una versión antigua. Guarda la factura, sus tramos, las correcciones y la auditoría;
marca el fichero como confirmado y solo entonces borra el borrador, todo dentro de la misma operación.

Si cualquier comprobación falla, la factura no queda a medias y el borrador sigue disponible para continuar.
La foto original tampoco se toca durante este paso.

### Confirmar y continuar con la siguiente (R-025, 21/08/2026)

Después de guardar una factura, la aplicación vuelve a preguntar qué queda pendiente en la bandeja. Si hay
otra factura lista para revisar, abre automáticamente la primera; no decide cuál es antes de que el servidor
haya confirmado la actual. Si no queda ninguna, vuelve a **Mis facturas**.

### Supervisión de pendientes del equipo (R-026, 21/08/2026)

El administrador de la asesoría tiene ahora una pantalla separada, **Pendientes del equipo**, donde ve las
subidas pendientes de otras personas: quién la subió, empresa, estado, fecha, dirección y número de páginas.
No mezcla esa vista con **Mis facturas**, que sigue siendo estrictamente personal.

Puede abrir un pendiente para consultar la revisión, pero esa apertura usa una puerta de solo lectura. En esa
pantalla no existen botones para guardar, confirmar ni confirmar y siguiente; el borrador continúa perteneciendo
al usuario que subió el documento.

### Supervisión global admin-tech (R-027, 21/08/2026)

El usuario técnico de plataforma tiene una pantalla separada para ver pendientes de todas las asesorías. La
lista muestra primero solo datos de control, como tenant, empresa, usuario y estado. El contenido de un documento
no se abre automáticamente: hay que pulsar **Abrir en solo lectura**.

Cada apertura se registra con el usuario técnico, la asesoría afectada, el documento, el identificador de la
petición y la IP de origen. La consulta se ejecuta entrando explícitamente en el contexto de esa asesoría, en
vez de usar una consulta global que pudiera saltarse las barreras de aislamiento. La primera versión ya está
cableada en backend y frontend, con paginación estable mediante un cursor que permite continuar sin
repetir ni saltar documentos.

### Retención de documentos no confirmados (R-028, 22/08/2026)

Un job diario busca documentos que llevan más de 90 días sin confirmarse. Primero guarda las ubicaciones de
sus objetos, borra el borrador y las relaciones provisionales en la base de datos, registra una auditoría sin
datos personales y confirma la transacción. Solo después intenta borrar los objetos de MinIO.

Esto evita el problema peligroso de borrar primero el fichero físico y dejar la base de datos diciendo que
existe. Si MinIO está temporalmente caído, la base de datos sigue limpia y una métrica cuenta el fallo para
que operaciones pueda detectarlo y reintentarlo.

### Mistral con campos estructurados (R-029, 22/08/2026)

Mistral ya no se trata como si nunca pudiera devolver campos de factura. Se le envía un contrato JSON que
indica exactamente qué debe devolver: fecha, número, importes, tramos de IVA e identificadores fiscales.
Los importes viajan como texto, por ejemplo `"121.00"`, para no perder céntimos por redondeos, y dentro de
la aplicación se convierten a `Decimal`.

La respuesta se valida antes de entrar al resto del sistema. Si falta la anotación estructurada o está mal
formada, el motor falla de forma visible. Los campos extraídos conservan confianza baja porque la confianza
del proveedor por sí sola nunca confirma automáticamente una factura.

### Candidatos Gemini versionados (R-030, 22/08/2026)

La configuración ya no depende de nombres ambiguos como `preview` ni de un alias `latest`. El laboratorio
tiene tres candidatos identificables: Gemini 3.5 Flash, Gemini 3.6 Flash y Gemini 3.5 Flash-Lite.

La producción sigue apuntando a una versión elegida manualmente, Gemini 3.5 Flash. Que aparezca otro modelo
mejor en un benchmark no cambia la producción automáticamente; esa promoción requiere una decisión explícita.

### Contrato único de extracción OCR (R-031, 22/08/2026)

Los distintos lectores de IA ya hablan el mismo idioma al entregar una factura. El contrato común contiene
la versión del esquema, fecha, número, importes, IVA, IRPF e identificadores fiscales. Los importes siempre
son texto al cruzar la frontera de cada proveedor y se convierten a números decimales dentro de Autofactu.

Así Gemini, Claude, Azure OpenAI y Mistral pueden compararse sin que cada uno invente nombres de campos o
reglas distintas. Las respuestas antiguas todavía se pueden leer para no romper datos ya generados, pero las
nuevas deben cumplir el esquema versionado.

### Producción OCR y laboratorio separados (R-046, 22/08/2026)

El panel técnico ya distingue dos cosas que antes estaban mezcladas: el lector que usa la aplicación para
las facturas reales y el laboratorio donde se prueban otros motores y variantes. Apagar el benchmark
automático detiene las llamadas experimentales, pero no cambia el lector fijo de producción.

La base de datos guarda estos controles separados. El botón de promoción pide confirmación y deja una
traza permanente con la política anterior, la nueva, quién la promovió y cuándo. Así una prueba no puede
cambiar la producción por accidente ni quedar sin explicación.

### Telemetría sin datos privados (R-047, 22/08/2026)

Autofactu ahora mide cuánto tarda una subida, cuánto espera una factura en la cola, cuánto tarda el OCR,
cuándo se usa el segundo lector, cuánto tarda guardar un borrador y cuánto tiempo pasa hasta confirmar.
También publica contadores agregados de documentos pendientes, listos y caducados.

Estas métricas sirven para saber si el sistema está sano sin enviar a Prometheus datos de facturas. Nunca se
usan como etiquetas el CIF, el proveedor, el número de factura ni el importe. El número de páginas se agrupa
en tramos para evitar crear miles de métricas diferentes.

### ETA honesta del OCR (R-048, 22/08/2026)

La pantalla puede mostrar cuánto falta solo cuando Autofactu ya tiene al menos 30 lecturas terminadas de
la misma combinación de motor, modelo y tamaño del documento. Calcula las tandas según los trabajadores
disponibles y muestra un intervalo, por ejemplo 20-35 segundos. Si todavía no hay suficientes datos, no
inventa una cifra y deja la ETA sin mostrar.

### Verificación HTTP de la ETA (R-048, 27/08/2026)

Además de probar el cálculo aislado, se comprobó el recorrido real: se guardaron 30 muestras en Postgres
y se consultó el endpoint de estado bajo las reglas de privacidad. Con una factura delante, cuatro trabajos
posibles, cinco segundos de espera y veinte de procesamiento, la API devolvió un intervalo de 25 a 30
segundos. La misma prueba confirma que con menos de 30 muestras no aparece una cifra. Falta comprobar la
representación visual en la pantalla durante staging.

### Endurecimiento del flujo OCR (R-049, 22/08/2026)

Se separó la puerta de “puedo leer” de la puerta de “puedo modificar”. Un administrador de asesoría
puede abrir una factura pendiente de otra persona para supervisarla, pero no puede guardar su borrador,
confirmarla ni reintentar su OCR. La pantalla de supervisión y la apertura del administrador técnico usan
un camino de solo lectura.

Además, la API ordena al navegador y a los proxies no guardar respuestas ni imágenes privadas, y al cerrar
sesión se limpia la caché de datos de la cuenta anterior. La validación completa contra servicios reales
queda pendiente de disponer de Redis y Postgres.

### Preparación de la prueba de carga OCR (R-050, 22/08/2026)

Se ha preparado un arnés que lanza 100 subidas simultáneas, diez por cada uno de diez usuarios, y comprueba
que cada usuario solo ve sus propios documentos. El informe mide p50/p95, respuestas `429`, estados OCR,
pool de Postgres, Redis y recuperación, sin guardar correos ni datos fiscales.

La prueba real necesita un entorno de staging con Postgres, Redis, MinIO, antivirus y worker OCR. Por eso
esta fase queda pendiente de ejecución empírica y no se presenta como una garantía de rendimiento de producción.

### Rollout reversible por fases (R-051, 22/08/2026)

Autofactu ya tiene un conjunto cerrado de interruptores de despliegue. Permiten activar una capacidad
primero en pruebas, después para un tenant piloto y ampliar progresivamente. Si algo sale mal, se apaga
el interruptor y se vuelve al flujo anterior sin borrar facturas ni deshacer migraciones.

El aprendizaje agregado de proveedores, la bandeja personal, el guardado automático de borradores, la
captura multipágina y las etapas de procesamiento ya consumen estos interruptores. Si se apaga el scanner
nuevo, se conserva la captura completa sin recorte OpenCV; si se apaga la política OCR nueva, se vuelve al
primario legacy Gemini 3 Flash. `/auth/me` entrega al navegador solo el resultado de la evaluación para su
tenant, nunca la lista interna de tenants piloto.

### Rollback del scanner y de la política OCR (R-051, 23/08/2026)

Los dos interruptores que faltaban ya tienen una vuelta atrás segura. Si se apaga el scanner nuevo,
Autofactu conserva la foto completa y no intenta detectar bordes con OpenCV. Si se apaga la política OCR
nueva, el worker vuelve al lector Gemini 3 Flash que se usaba antes de la política versionada, sin activar
un segundo lector ni consultar la configuración nueva. Ambos cambios son de configuración y no requieren
deshacer migraciones.

### Preflight del canario (R-051, 23/08/2026)

Antes de activar el canario existe un comprobador que revisa que los siete interruptores sean booleanos,
que la lista de tenants piloto contenga UUIDs válidos y que staging tenga sus secretos mínimos. No muestra
ningún secreto. Si falla, el despliegue se detiene antes de probar con usuarios reales; aun pasando, todavía
hay que comprobar conectividad y ejecutar el canario funcional.

### Canario técnico de Setex (R-051, 25/08/2026)

Se activaron los siete interruptores únicamente para el tenant piloto Setex mediante su UUID. El preflight
devolvió `ready: true`, la API y el worker cargaron la misma configuración, y otro tenant de laboratorio
mantiene todos los interruptores apagados. La configuración no publica la allowlist ni los secretos al
navegador.

Durante la comprobación se detectó que la base de datos estaba en la migración `0040` mientras el código
actual necesitaba migraciones posteriores. Se aplicaron de forma transaccional las migraciones `0041` a
`0054`, incluida la columna `ready` de la telemetría OCR y las estructuras de R-051. Después, health y
métricas respondieron correctamente (`200`), Alembic quedó en `0054` y pasaron las nueve pruebas focalizadas
de flags y preflight. Falta únicamente una prueba funcional con una factura real de Setex, que necesita
credenciales y elegir explícitamente el documento de prueba.

### Aislamiento de las suites de pruebas (25/08/2026)

Las pruebas que necesitan una base de datos real crean una base efímera. En Docker, dos contenedores
distintos pueden tener el mismo número de proceso, así que usar solo el PID podía hacer que una suite
borrase la base de otra. Ahora cada ejecución añade un identificador aleatorio al nombre de su base.

El Redis de test sigue usando el índice `/15` y cada caso lo limpia con `flushdb()`. Por eso las suites
completas no deben lanzarse en paralelo hasta separar también ese espacio de Redis; la aplicación normal
no comparte este mecanismo de pruebas.

### Esquema ORM y migraciones alineados (R-051, 23/08/2026)

El robot de CI también comprueba que los modelos que usa el programa y la estructura real de la base de
datos cuentan la misma historia. Se corrigieron varias diferencias de descripción: metadatos de auditoría,
contadores de retención, restricciones de proveedor e índices y restricciones de las muestras ETA del OCR.
No se cambió información ni se deshizo ninguna migración: se hizo que el mapa que usa el programa refleje
correctamente el archivador que las migraciones ya construyen.

### Correcciones de CI descubiertas al cerrar R-051 (23/08/2026)

Al desbloquear la comprobación del esquema, el robot pudo ejecutar toda la batería de pruebas y encontró
cinco comportamientos antiguos que estaban ocultos detrás del fallo anterior: la supervisión de una
asesoría no podía leer correctamente sus perfiles de proveedor, un permiso se traducía en un error 404,
y dos tests seguían usando nombres o datos de contratos que ya habían cambiado. Se corrigieron con una
migración compatible, respuestas HTTP precisas y tests actualizados; el comportamiento de negocio no se
relajó ni se expusieron datos entre asesorías.

### Scanner en segundo plano (R-004, 23/08/2026)

La cámara ya puede analizar continuamente una versión pequeña de la imagen sin bloquear la pantalla:
ese trabajo se ejecuta en un **Web Worker**, que es un ayudante separado del hilo que dibuja la interfaz.
El coordinador solo permite una imagen pendiente a la vez; si llega otra mientras el ayudante está ocupado,
se descarta en lugar de acumular una cola que haría que el análisis fuese antiguo. Además, cada petición lleva
un número y se ignoran las respuestas atrasadas de peticiones anteriores.

El navegador usa `requestVideoFrameCallback` cuando lo ofrece y un temporizador como alternativa cuando no.
El worker también deja preparado el protocolo para analizar una imagen fija y procesar la imagen final. La
suite frontend completa (371 tests) y el build pasan; queda probar la experiencia en un navegador y teléfono
reales.

### Detector y puerta de calidad (R-005/R-006, 23/08/2026)

El detector ya no elige automáticamente el contorno más grande. Compara cada candidato por tamaño,
forma rectangular, convexidad, posición en el centro, continuidad del borde, distancia a los márgenes y
proporción razonable de una factura. También indica qué método encontró las esquinas y cuánta confianza
merece ese resultado.

La puerta de calidad es una comprobación separada que decide por qué una imagen todavía no está lista para
AUTO: no hay documento, tiene poca confianza, es pequeño, está cortado, borroso, oscuro, quemado, demasiado
inclinado o se está moviendo. Solo devuelve `ready` cuando todas las señales cumplen sus umbrales.

### Máquina AUTO/MANUAL y lock de captura (R-007, 23/08/2026)

La captura tiene una máquina de estados preparada para pasar por escaneando, estabilización, armado AUTO,
captura, procesado, preview, subida y aceptación. Cambiar entre AUTO y MANUAL borra la estabilidad anterior.
Además, un lock compartido impide que dos toques rápidos creen dos procesados o dos subidas de la misma foto.
La UI completa para cambiar de modo queda pendiente de la siguiente iteración.

### Polígono de la factura en pantalla (R-008, 23/08/2026)

La cámara ahora puede dibujar encima del vídeo las cuatro esquinas que ha encontrado. El cálculo tiene en
cuenta que `object-cover` agranda la imagen hasta llenar la pantalla y recorta los lados sobrantes; por eso
el polígono no se desplaza ni se deforma en un móvil vertical. Se usa un SVG ligero, no un canvas que redibuje
la pantalla completa continuamente.

Cuando aún no hay detección se muestra una guía tenue; cuando hay detección aparece el amarillo y, cuando la
confianza y el tamaño son suficientes, se intensifica. Las esquinas del preview reducido se convierten de
nuevo a la resolución original del vídeo antes de dibujarse.

### Captura HD y redetección final (R-009, 23/08/2026)

Al pulsar «Capturar foto», el navegador intenta obtener una fotografía de la cámara con su resolución
real mediante `ImageCapture`, en vez de quedarse necesariamente con el fotograma pequeño que se estaba
viendo en pantalla. Si el navegador no ofrece esa función, se usa el canvas como alternativa compatible.

Para no gastar OpenCV trabajando con una imagen enorme, se crea una copia de análisis de hasta 1600 píxeles
de lado largo. Las esquinas encontradas en esa copia se devuelven a las coordenadas del still HD original
antes de recortar y enderezar. De esta forma el polígono del preview sirve de orientación, pero la foto final
se vuelve a comprobar sobre la imagen que realmente se va a guardar.

### Preview obligatoria antes de guardar (R-010, 23/08/2026)

Una captura individual ya no se envía inmediatamente. Primero aparece una pantalla con la foto y dos
decisiones claras: **Repetir**, que revoca la imagen temporal y vuelve a abrir la cámara sin llamar al
servidor, o **Usar foto**, que adquiere el lock, muestra «Guardando factura…» y entonces realiza la subida.
El selector de archivos sigue la misma regla. Las capturas multipágina mantienen su panel de miniaturas,
porque ese panel ya permite revisar, quitar y ordenar páginas antes del envío.

### Subida aceptada y OCR separado (R-011, 23/08/2026)

La aplicación distingue entre «la petición llegó» y «la factura se aceptó». El frontend solo considera
correcta una respuesta `201` con un identificador de fichero; un `200`, `202` u otro código no se trata como
guardado. El único desvío intencionado es `409` con `duplicate_of`, que lleva al documento propio original.

El servidor responde después de guardar el fichero en estado `pending_ocr` y agenda el lector OCR después del
commit de la base de datos. Por eso el usuario no queda esperando a que termine la inteligencia artificial y
el worker nunca puede leer una fila que todavía no esté confirmada en la base de datos.

### Captura de varias facturas (R-012, 24/08/2026)

«Varias facturas» no es lo mismo que «varias hojas». En el primer modo cada foto confirmada hace una petición
individual y crea su propio `uploaded_file`; cuando llega el `201`, la siguiente foto queda habilitada. La
sesión de la pantalla guarda un identificador UX, el orden y la hora de cada aceptación, hasta un máximo de
diez facturas sin obligar a llegar a diez.

Si el servidor responde que una factura ya estaba subida, se muestra un aviso discreto y no se vuelve a contar
el mismo `fileId`. La pantalla envía el UUID de sesión y el número de orden como metadatos opcionales de cada
subida. R-013 los guarda en `uploaded_files` y permite recuperar la sesión ordenada, sin crear una tabla de
sesiones ni convertir ese identificador en una regla de autorización.

### Agrupación durable de captura (R-013, 24/08/2026)

Cada fila puede llevar `capture_session_id` y `capture_sequence`. Ambos son opcionales y deben llegar juntos;
la secuencia aceptada está entre 1 y 50. La base de datos comprueba esa relación e incluye un índice parcial
por tenant, usuario, sesión y orden para recuperar las fotos con rapidez. La autorización sigue viniendo
del JWT, el tenant, `uploaded_by` y RLS: conocer un UUID de sesión no permite ver ni editar documentos ajenos.

### Después de subir y mantener la cámara (R-014/R-015, 24/08/2026)

Una subida simple ya no fuerza la pantalla de confirmación. Primero muestra que el fichero fue aceptado y
ofrece dos decisiones: abrir su progreso/revisión cuando corresponda o ir a «Mis facturas». La revisión no
se abre por sorpresa mientras el OCR sigue trabajando.

En «Varias facturas», la cámara permanece abierta mientras se prepara y se sube una foto. Cuando llega el
`201`, la misma cámara vuelve a estar disponible sin pedir permiso otra vez. Si el sistema operativo ha
terminado el track, la aplicación lo detecta por `readyState` y solo entonces solicita una cámara nueva.

### Retos de lectura de estructura (R-041/R-042, 24/08/2026)

Además del lector principal de facturas, ahora existen dos servicios de laboratorio para comparar si otros
programas entienden mejor la estructura visual de una factura: PaddleOCR/PP-StructureV3 y Surya. No se
instalan dentro de la API ni se ejecutan para clientes automáticamente. Solo se levantan con el perfil
opcional `lab` de Docker Compose y devuelven medidas comparables de líneas de impuestos, tablas, columnas,
relación etiqueta/valor y orden de lectura. Así se puede medir una mejora real antes de asumir el coste de
añadir otro motor a producción.

La primera prueba real también enseñó por qué siguen siendo servicios de laboratorio: Paddle necesita una
configuración especial de memoria y de oneDNN para sus modelos grandes, y Surya 2 en CPU tarda demasiado
para el uso normal. El servicio Paddle tiene ahora un modo ligero (`PADDLE_PIPELINE=ocr`) como opción
predeterminada; el modo estructural completo se construye aparte con sus dependencias pesadas. Por eso
ninguno sustituye todavía al lector principal. Surya queda aparcado hasta tener una GPU o un servidor
externo; Paddle solo podrá compararse de verdad cuando su caché de modelos y su memoria estén preparados
en un entorno de benchmark.

### Separación de colas de usuario y laboratorio (R-043/R-044, 24/08/2026)

El trabajo que afecta a una persona y el trabajo experimental ya tienen dos colas distintas. La cola
principal atiende la lectura de facturas y sus reintentos; la cola de fondo atiende comparativas,
benchmarks y challengers. Además, el worker principal puede procesar cuatro trabajos a la vez y el de
laboratorio solo uno, para que una prueba pesada no deje esperando a los usuarios. El cableado se probó
encolando y consumiendo un trabajo real contra Redis.

### Cortacircuitos del proveedor (R-045, 24/08/2026)

Si un proveedor de OCR empieza a fallar repetidamente, el sistema deja de llamarlo durante unos segundos
en vez de multiplicar el problema. Tras ese descanso solo deja pasar una prueba. Esa prueba se reserva
con una llave temporal de Redis usando una operación atómica, de modo que dos workers no puedan probar a la
vez. Si funciona, el circuito se cierra; si vuelve a fallar, sigue abierto.

### Controles separados para producción y laboratorio (R-046, 24/08/2026)

El panel de administración técnica distingue ahora la configuración que usa producción de la
configuración del laboratorio. Producción muestra su motor, modelo, fallback, consenso y versión de
política. El laboratorio tiene sus propios controles de visibilidad, benchmark automático, motores y
variantes. El botón de desactivación apaga solo los benchmarks automáticos: la producción sigue usando
su política fija. Una promoción a producción exige confirmación y guarda una copia de la política
anterior, la nueva, el administrador y la fecha en un registro que no se puede modificar ni borrar.

### Telemetría y estimación prudente (R-047/R-048, 24/08/2026)

La aplicación publica métricas Prometheus de subida, espera y procesamiento OCR, fallback, fallos,
borradores, revisión y tamaños de las colas. Las etiquetas están limitadas a datos técnicos y a grupos
de número de páginas; nunca incluyen CIF, proveedor, número de factura ni importes. La pantalla solo
calcula una ETA cuando existen al menos 30 ejecuciones recientes comparables. En ese caso muestra un
rango aproximado teniendo en cuenta la concurrencia; si no hay suficientes datos, no inventa segundos.

### Prueba de carga y recuperación (R-050, 24/08/2026)

Existe un arnés que prepara el escenario de diez usuarios con diez subidas cada uno, mide el p50 y el
p95, espera el resultado del OCR y comprueba que cada usuario solo ve su propia bandeja. El informe no
guarda credenciales ni datos fiscales. Además de la profundidad y disponibilidad de Redis, ahora separa
el estado de recuperación: pendientes, procesando, abandonados, fallidos y documentos expirados. La
caída y recuperación de Redis se ejecuta manualmente en staging con un proveedor OCR de prueba, nunca
contra servicios de pago.

### Primera ejecución sintética de carga OCR (R-050, 26/08/2026)

Se ejecutó la primera tanda real de 100 subidas en un tenant efímero separado de Setex. El entorno usó
Redis en la base `/15`, MinIO, ClamAV y un extractor OCR determinista de `APP_ENV=load_test`, por lo que
no llamó a Gemini ni generó coste. Las 100 peticiones respondieron `201`, las 100 facturas acabaron en
`needs_review`, no hubo `429` y ningún usuario vio documentos de otro usuario.

El p50 fue `3,68 s` y el p95 `4,44 s`. El p95 todavía supera el objetivo de `3 s`, así que R-050 sigue
abierto aunque la parte de aislamiento, cola y estados terminales haya pasado. Las métricas de recuperación
son globales para toda la instalación; por eso el informe guarda una línea base y un delta. El único
fallo que aparecía en la foto global era anterior y pertenecía a otro tenant; el delta de la prueba fue
cero. El tenant sintético, sus documentos y los contenedores temporales se eliminaron al terminar.

### Interrupción y recuperación de Redis en una subida (R-050, 26/08/2026)

Se hizo una segunda comprobación más agresiva con una cola Redis exclusiva. Tras completar los diez
logins, se dejaron pasar algunas subidas y se apagó Redis: 8 peticiones fueron aceptadas y 92 fallaron
durante la caída. Las 8 aceptadas no desaparecieron: quedaron guardadas en Postgres, 7 ya procesadas y 1
pendiente de OCR. Se vació únicamente la base Redis de pruebas para representar un trabajo cuyo encolado
se perdió, se arrancó el recuperador y este volvió a poner el pendiente en la cola. El worker terminó los
8 documentos en `needs_review` usando el lector determinista de prueba, sin Gemini ni coste externo.

Esto demuestra la diferencia entre "la subida se ha guardado" y "el trabajo en segundo plano ya se ha
hecho": aunque Redis se caiga, la foto aceptada sigue en el archivador permanente y se puede volver a
poner en la lista de trabajo. R-050 continúa abierto únicamente porque el p95 de subida medido fue mayor
que el objetivo de 3 segundos.

Para intentar reducir ese tiempo se dejó de preguntar a MinIO en cada subida si el bucket del tenant ya
existe, manteniendo una comprobación de seguridad si MinIO dice que ha desaparecido. También se juntaron
en un solo `EVAL` atómico los dos contadores Redis del límite de subidas y se redujo un viaje a Postgres
al fijar simultáneamente el tenant y la empresa. La repetición válida más reciente quedó en `3,26 s` de
p95, con cero fugas entre usuarios; sigue por encima de los 3 segundos, así que R-050 aún no está cerrado.

Para no tocar la base de datos a ciegas se midieron sus planes reales. Las búsquedas de duplicados usan las
restricciones únicas de empresa, usuario y hash; con la instalación actual tardaron `0,03 ms` para la fila
principal y `0,09 ms` incluyendo las páginas. Por tanto no se añadió un índice especulativo: las décimas
restantes del p95 están en la coordinación y el I/O del camino completo, no en esas búsquedas SQL.

### Aislamiento y recuperación ante errores (R-049/R-051, 24/08/2026)

La comprobación de seguridad contra accesos cruzados entre asesorías pasa con Postgres, Redis y MinIO
reales: un usuario no puede operar sobre facturas ajenas ni ver la bandeja de otro usuario. Los flags de
despliegue forman una lista cerrada y pueden apagarse sin deshacer migraciones. El preflight del canario
comprueba los siete flags, la allowlist y la presencia de secretos, pero nunca imprime sus valores.

### Preparación del host y PaddleOCR (25/08/2026)

El servidor donde vive Autoken se ha preparado para probar PaddleOCR sin depender del ordenador de Julio:
se actualizaron los paquetes del sistema y Docker Compose, se añadieron 4 GiB de memoria de emergencia y se
dejó el laboratorio separado del API y de la web, con un límite de 2 CPU y 6 GiB de RAM. La caché de modelos
queda guardada en un volumen persistente, así que apagar o recrear el contenedor no obliga a descargarla otra
vez.

PaddleOCR está levantado solo en localhost, bajo el perfil de laboratorio, y no lee facturas de clientes ni
cambia el lector principal. El modelo medio que venía por defecto tardaba alrededor de 80-90 segundos por
factura en esta máquina; para poder experimentar se dejaron los modelos `PP-OCRv5_mobile` y
`latin_PP-OCRv5_mobile_rec` como predeterminados, que tardan aproximadamente 27-35 segundos. La primera
factura real procesada devolvió texto, IVA, campos y orden de lectura. Eso demuestra que el servicio funciona,
pero todavía hace falta comparar su precisión con la verdad humana antes de decidir si merece entrar en
producción.

### Cuenta de soporte para prueba móvil (25/08/2026)

La cuenta `soporte@autoken.es` se conserva como usuario normal (`user`) activo para probar Autofactu
desde un móvil. En el tenant real `setex`, tiene exactamente una empresa asignada: **Estudio Inghervi,
S.L.U.**, CIF **B06400980**. Esa es la única dirección correcta para la prueba:
`https://setex.autoken.es`.

Se retiró la asociación de la empresa demo "Empresa Fantasma (prueba soporte)" en `ilex`. Como Inghervi
no pertenece al tenant demo `ilex`, soporte no tiene empresa ni acceso de usuario allí. No se borró la
empresa demo ni ningún documento; solo se quitó la asociación de la cuenta y se dejó registro de auditoría.

### Corrección de lectura de importes españoles (25/08/2026)

La prueba móvil descubrió que la foto sí llegaba al servidor, pero el lector automático fallaba al
recibir importes escritos con coma decimal, como `450,00`. El lector entiende ese formato, pero una
pieza posterior intentaba convertirlo como si fuera un número inglés y marcaba toda la factura como
fallida. Se corrigió esa conversión para aceptar formatos españoles e ingleses, incluyendo separadores
de miles. La misma factura real se volvió a procesar y terminó en `needs_review`, con sus importes
disponibles para que la persona los revise, en lugar de mostrar el error y pedir otra foto.
También se corrigió el permiso interno que guarda las muestras de tiempo del lector, para que el
indicador de tiempo estimado pueda aprender de las facturas procesadas sin dar acceso directo de
escritura a la aplicación.

### Verificación del siguiente paso de Autofactu (26/08/2026)

La aplicación web queda comprobada con 410 tests, comprobación de tipos y build de producción. También
se actualizó el registro técnico a la migración `0056`, que es la versión real de la base de datos.
El siguiente ensayo importante es R-050: 100 subidas sintéticas para medir carga, recuperación y
aislamiento entre usuarios. No se ejecutará contra Setex porque el entorno actual usa Gemini real y el
ensayo necesita un proveedor OCR controlado y diez usuarios de prueba; hacerlo sin eso produciría coste
y datos de prueba en el tenant real.

### Runbook general de rollback (26/08/2026)

Se añadió `docs/runbooks/rollback.md` como procedimiento único para responder a incidentes. Primero
explica el rollback funcional de una feature mediante flags, que conserva los datos y no necesita tocar
Alembic. Después separa el rollback de una imagen, el downgrade excepcional de una migración y la
restauración desde backup, siempre con API/worker controlados, backup verificado y comprobaciones de
health, métricas, cola, ClamAV y aislamiento. No se permite arreglar el esquema borrando datos o con SQL
manual, ni restaurar directamente encima de producción.

### Acceso web por rol y corrección del proxy (26/08/2026)

Se verificaron las tres entradas públicas: `panel-staging.autoken.es` para los administradores de
plataforma, y `setex.autoken.es` para el administrador de asesoría y el usuario `soporte`. Los dominios
tenían HTTPS válido y el frontend cargaba, pero el stack se había arrancado sin el overlay de producción;
por eso Nginx devolvía la página web también para las llamadas `/api/*`. Se relanzaron API, worker y
frontend con ambos ficheros Compose y se reinició Traefik. Ahora `/api/v1/health` llega a FastAPI y una
petición sin sesión a `/api/v1/auth/me` recibe `401` JSON. El procedimiento de acceso y diagnóstico queda
en `docs/runbooks/acceso-web.md`.

### Protección definitiva del despliegue Traefik (26/08/2026)

El incidente anterior podía repetirse porque Docker Compose permite ejecutar el fichero base sin el
overlay de producción. Se añadió `DEPLOYMENT_PROFILE`: la pila base fija `standalone`, el overlay real
fija `proxy`, y API/worker se niegan a arrancar en `staging` o `production` si no reciben `proxy`.
Además, `infrastructure/deploy.sh` es ahora el punto de entrada del despliegue público: reconstruye las
imágenes, espera los healthchecks, comprueba la red externa `proxy`, verifica las etiquetas de routers
Traefik y consulta el health JSON por HTTPS. La decisión arquitectónica está registrada en
`docs/adr/0020-despliegue-publico-con-overlay-proxy.md`.

### Prueba funcional real del canario (26/08/2026)

Se probó una factura nueva desde el móvil usando `soporte@autoken.es` en `setex.autoken.es`, con la
empresa **Estudio Inghervi, S.L.U.**. La foto llegó, el lector entendió la factura emitida y el usuario la
revisó y confirmó. La factura quedó guardada con base de **1.100,00 €**, IVA de **231,00 €**, IRPF de
**209,00 €** y total de **1.122,00 €**; el cuadre es correcto porque `1.100 + 231 - 209 = 1.122`.

El lector la dejó en `needs_review` antes de la confirmación porque varios importes tenían confianza baja.
Eso significa «hay que revisarla», no «la foto ha fallado». Esta prueba confirma que el canario de R-051
funciona de punta a punta con una factura real. Sigue pendiente únicamente cerrar R-050 por latencia y
completar la verificación general de staging.

### Coordinación de la primera subida de un tenant (26/08/2026)

Cuando una asesoría nueva recibe su primera factura, la aplicación debe crear su espacio privado en MinIO.
Con muchas subidas simultáneas, varias peticiones podían intentar crearlo a la vez y repetir trabajo. Ahora
solo una petición comprueba y crea ese espacio por tenant; las demás esperan un instante y reutilizan el
resultado. Los tenants distintos no se bloquean entre sí. La regresión concurrente pasa y se mantiene el
requisito de que una factura nunca se guarda sin haber pasado antes por el antivirus.

La oleada de control posterior aceptó las 100 facturas, procesó las 100 con el lector de prueba y no
mezcló ninguna bandeja entre usuarios. Su p95 fue **4,52 segundos**, peor que la mejor medición anterior
de 3,26 segundos, así que esta corrección arregla una carrera concreta pero no resuelve todavía el objetivo
de latencia. R-050 sigue abierto hasta encontrar la causa del tiempo restante o justificar formalmente el
objetivo en un entorno de red razonable.

### Medición del tiempo por etapas de una subida (26/08/2026)

Para investigar el retraso sin adivinar, la aplicación ahora mide por separado las etapas técnicas de una
subida: permisos, límite de frecuencia, lectura, validación, deduplicación, antivirus, MinIO y guardado en
la base de datos. Solo guarda tiempos agrupados; no guarda nombres, usuarios ni facturas dentro de estas
métricas.

En la nueva medición las 100 subidas fueron aceptadas, pero el p95 subió a **5,01 segundos**. El mayor
tiempo acumulado apareció al comprobar duplicados y guardar los registros cuando todo ocurre a la vez. El
antivirus y MinIO fueron bastante menores, así que el siguiente trabajo debe estudiar la espera y la
coordinación de las conexiones de base de datos y Redis. Esta ejecución es diagnóstica, no sustituye la
mejor evidencia anterior porque la bandeja estaba desactivada para ese tenant de prueba.

### Medición de la identidad y del tamaño del pool (26/08/2026)

También medimos el paso que ocurre antes de entrar en la función de subida: comprobar en la base de
datos a qué empresa pertenece el usuario. En una corrida con la bandeja habilitada para el tenant
efímero, las 100 subidas fueron aceptadas, no hubo fugas entre usuarios y el p95 fue **3,94 segundos**.
La resolución de empresa acumuló **41,61 segundos** y el guardado/deduplicación siguieron siendo las
etapas más costosas.

Probamos reducir el tamaño del pool de conexiones a `30` sin conexiones extra. Aunque las subidas fueron
aceptadas, el sistema se quedó sin conexiones al consultar los estados y acabó en timeout. Por eso no se
aplica ese ajuste: el overflow es una reserva necesaria cuando coinciden subidas y consultas. Tampoco se
añade una caché de pertenencia, porque podría mantener permisos revocados durante unos segundos.

También probamos desactivar temporalmente el `pre-ping`, que es una comprobación para no reutilizar una
conexión muerta con la base de datos. El p95 bajó solo de **3,94 a 3,86 segundos** y siguió sin cumplir el
objetivo. Como esa comprobación protege frente a caídas de red o de Postgres, se mantiene activa por
defecto y no se considera una solución.

Finalmente se midió por separado el tiempo de conseguir una conexión y preparar su contexto privado de
RLS. En la última prueba, esa preparación acumuló **24,83 segundos** en identidad, **33,05** al comprobar
duplicados y **22,32** al guardar. Esto confirma que parte del retraso es esperar/preparar conexiones
cuando coinciden muchas peticiones, no procesar la imagen. No se aumenta el pool sin calcular antes el
límite total de conexiones de Postgres para la API, el worker y las réplicas.

También probamos pools más grandes. El ajuste `30/0` dejó al sistema sin conexiones durante las consultas
de estado y `40/20` fue incluso más lento, con un p95 de **4,86 segundos**. El tamaño actual `20/20` es el
mejor equilibrio medido; el retraso no se arregla simplemente abriendo más conexiones.

En la persistencia de una subida, la factura y su registro de auditoría se insertan en una sola operación
de base de datos. Así se elimina un viaje de ida y vuelta sin perder la garantía de que ambos se guardan o
ninguno. La prueba confirmó la garantía, pero el tiempo total aún queda por encima del objetivo de 3 s.

### Decisión de prioridad de R-050 (26/08/2026)

Julio ha decidido que el objetivo de tres segundos no es un bloqueo de producto. El flujo completo puede
tardar aproximadamente entre ocho y diez segundos si mantiene las garantías importantes: la factura se
acepta solo después del antivirus, no aparecen documentos de otros usuarios, el registro y la auditoría
se guardan juntos y las subidas aceptadas se recuperan correctamente si falla la cola OCR. Por tanto, no
se seguirá complicando el código para arañar milisegundos en el camino caliente; R-050 queda pendiente
únicamente de la verificación completa de staging y recuperación.

La última medición funcional válida aceptó las 100 subidas y no produjo fugas. La migración `0056_r050_ctx`
reduce viajes de ida y vuelta en las comprobaciones RLS mediante funciones PostgreSQL acotadas, sin guardar
permisos en caché ni retrasar revocaciones. Los gates focalizados de aislamiento, cabeceras, ETA, rollout
y arnés pasan contra los servicios reales.

### Verificación HTTP de la ETA (R-048, 27/08/2026)

Además de probar el cálculo aislado, se comprobó el recorrido real: se guardaron 30 muestras en Postgres
y se consultó el endpoint de estado bajo las reglas de privacidad. Con una factura delante, cuatro trabajos
posibles, cinco segundos de espera y veinte de procesamiento, la API devolvió un intervalo de 25 a 30
segundos. La misma prueba confirma que con menos de 30 muestras no aparece una cifra. Falta comprobar la
representación visual en la pantalla durante staging.

### Estado actual de la carga y del despliegue (27/08/2026)

La carga sintética ya ha demostrado `100/100` subidas aceptadas, cero fugas entre usuarios, auditoría
atómica y recuperación de documentos aceptados tras una caída de Redis. El p95 observado ronda 3,6-4,0
segundos en las ejecuciones válidas; Julio ha decidido que el límite estricto de 3 segundos no bloquea si
se conservan las garantías de integridad y aislamiento. R-050 y R-051 siguen abiertos únicamente para la
verificación completa de staging, canario y rollback con el entorno final.

El despliegue de staging quedó comprobado con el procedimiento oficial. API y worker arrancan con la
protección `proxy`, Traefik dirige `/api` al servidor correcto y los dos dominios públicos devuelven el
JSON de salud de FastAPI en lugar de la página web. El siguiente paso ya no es corregir infraestructura:
es ejecutar la prueba de carga/recuperación y hacer el canario guiado con la factura que Julio elija.

### Nueva prueba manual del canario (27/08/2026)

Julio subió otra factura desde el navegador. El servidor la aceptó con `201`, la inteligencia artificial la
leyó en unos 12 segundos y la dejó en `needs_review`, que significa que la persona debe revisar los datos,
no que la lectura haya fallado. Después se guardó la revisión y se confirmó la factura. El archivador de
Postgres terminó mostrando el estado `confirmed`, sin errores de OCR ni de cola.

Esto confirma de nuevo el recorrido real de una factura, pero todavía no sustituye la prueba de 100 subidas
simultáneas, la recuperación después de apagar Redis ni la comprobación del rollback.

### Carga aislada y recuperación de Redis (R-050, 27/08/2026)

La prueba de muchas facturas se ejecutó sin tocar Setex: se levantaron una API, un worker y una Redis
temporales con un lector automático determinista. Diez usuarios sintéticos hicieron diez subidas cada uno.
Las 100 subidas fueron aceptadas, no hubo documentos cruzados ni respuestas `429`, y todas terminaron en un
estado final. El p95 fue de 3,97 segundos; se conserva la mejor medición anterior de 3,26 segundos como
referencia, porque cada corrida mide también la carga del host.

Después se apagó únicamente la Redis temporal durante otra oleada. Se aceptaron 69 facturas y 31 fueron
rechazadas mientras la cola estaba caída. Al restaurarla, el recuperador volvió a poner las 69 aceptadas en
la cola y el worker terminó todas, sin perderlas ni dejar ninguna pendiente. El tenant, usuarios, imágenes
y contenedores de prueba se borraron al finalizar.

### Proveedor OCR limitado por cuota (R-050, 27/08/2026)

También se probó el caso en que el lector principal responde `429`, que significa «demasiadas peticiones».
Un proveedor falso provocó esa respuesta y un lector alternativo falso completó la factura. Autofactu la
dejó correctamente en `ocr_done`, aumentó el contador técnico de respuestas `429` y no guardó el mensaje
del proveedor dentro de la factura. La prueba no llamó a Gemini ni utilizó credenciales reales.

También se comprobó la frontera del adaptador Gemini: aunque el SDK entregue el `429` solo como atributo
numérico y no dentro del texto del error, Autofactu conserva la clasificación para activar el tratamiento
correspondiente. El contenido original del proveedor no se propaga como dato de factura.

### Rollback de cualquier interruptor (R-051, 27/08/2026)

Se simuló el apagado de cada uno de los siete interruptores con el tenant piloto dentro de la lista
permitida. En todos los casos, `false` gana y la función queda desactivada. La simulación no cambió el
fichero real de configuración ni reinició el servidor. Para apagar un interruptor real de Setex todavía
hay que elegir cuál, observar el efecto y seguir el runbook con una confirmación explícita.

Después se hizo esa comprobación real con el interruptor de aprendizaje de proveedores, que es el menos
arriesgado: se apagó temporalmente, API y worker lo cargaron como `false`, health y preflight siguieron
correctos y los otros interruptores no cambiaron. Finalmente se restauró a `true`. No se deshicieron
migraciones ni se borró ningún dato.

### Auditoría final de infraestructura antes del go-live (27/08/2026)

La estructura real de la base de datos está en la migración `0056_r050_ctx`. Para comprobarlo no se usa la
cuenta normal de la aplicación, porque esa cuenta no debe poder modificar ni leer el control de migraciones;
se usa la herramienta administrativa separada. El resultado fue `0056_r050_ctx (head)`.

También se comprobó el backup nocturno: el 27 de agosto se creó un fichero cifrado de 373.833 bytes en
menos de un segundo y se subió a otra VPS. La copia y el restore drill ya habían sido comprobados antes.

La parte técnica está preparada, pero aún no se debe hacer el cambio definitivo: faltan aprobar la versión
de lanzamiento, decidir la noche de migración, confirmar exactamente las 51 empresas y 4 facturas que se
van a trasladar, cambiar el DNS definitivo y tener las credenciales del correo remitente.

### Base común de accesibilidad y branding del frontend (27/08/2026)

Se ha puesto una base común para las ventanas emergentes de la aplicación. Ahora una ventana tiene un
nombre que los lectores de pantalla pueden anunciar, coloca el cursor en el primer control al abrirse,
mantiene el teclado dentro de ella, se cierra con `Escape` y devuelve el cursor al sitio anterior al
cerrarse. Esto evita que cada pantalla tenga una versión ligeramente distinta y difícil de usar con
teclado.

También se conectó el color principal de los botones al color de la asesoría. Hasta ahora la aplicación
conocía el color configurado por cada tenant, pero muchas pantallas seguían pintando el naranja fijo de
Autoken. Ahora los botones principales respetan ese color sin cambiar la apariencia por defecto de
Autoken. La suite frontend queda en 410 tests, con typecheck y build correctos.

### Captura automática segura y modo manual (R-006/R-007, 27/08/2026)

La cámara ya no se limita a enseñar una guía: al abrirse empieza en modo automático y observa si la
factura está bien encuadrada, suficientemente nítida, bien iluminada, sin cortar los bordes y sin una
perspectiva extrema. Además exige que el documento permanezca quieto durante al menos 700 milisegundos
y cuatro imágenes antes de preparar la foto. Después espera 350 milisegundos más como confirmación para
evitar disparos accidentales.

El modo manual sigue siempre disponible. Ambos modos usan el mismo cierre de seguridad, por lo que una
doble pulsación o un evento automático y otro manual al mismo tiempo no pueden crear dos subidas. Si
faltan señales reales de calidad, el sistema no inventa valores: AUTO permanece sin armar y la persona
puede decidir si captura manualmente. Falta probarlo en teléfonos reales para ajustar los umbrales si
algún modelo de cámara se comporta distinto. La suite frontend queda en 419 tests.

### Recorte conservador y recuperación ante fallos de cámara (R-009, 27/08/2026)

Antes de recortar y enderezar una foto, Autofactu comprueba que las cuatro esquinas son números
válidos, están dentro de la imagen, no tocan el borde, ocupan una superficie razonable y no tienen una
perspectiva exagerada. Si una comprobación falla, conserva la foto completa en vez de fabricar un
recorte posiblemente incorrecto.

También se corrigió el camino de error de la cámara: si el dispositivo rechaza la captura, se libera
el cierre de seguridad y se puede volver a intentarlo. Durante una vista previa o mientras se procesa
una foto, el análisis automático queda temporalmente apagado para que no pueda iniciar una segunda
captura por detrás. La suite frontend queda en 433 tests.

### Transporte de subida separado y captura más resistente (R-009/R-011, 27/08/2026)

La subida simple y la subida de varias páginas ahora tienen cada una su propia función de transporte,
separada de los hooks que gestionan el estado visual. Esto hace más fácil comprobar que el navegador manda
exactamente las partes correctas del formulario y que solo se considera aceptada una respuesta `201`.
También se conserva la foto completa si falla el recorte de OpenCV, se cierran correctamente los recursos
temporales de imagen y se mantiene el último preview reciente mientras el lector en segundo plano está ocupado.
La suite frontend queda en 437 tests.

### Confirmación sin guardado innecesario del borrador (R-022, 27/08/2026)

Al confirmar una factura que ya tenía un borrador guardado, la pantalla intentaba guardarlo otra vez aunque
no se hubiera cambiado ningún dato. Si otra actualización había avanzado la revisión, el servidor respondía
`409` y la confirmación no llegaba a ejecutarse. Ahora solo se guarda el borrador cuando hay cambios pendientes
o se está recuperando un error anterior; si ya está limpio, se confirma directamente. La suite frontend queda
en 438 tests.

### Revisión explícita antes de confirmar (S2.4/S6.1, 27/08/2026)

La pantalla de revisión ya no pinta de rojo o amarillo los datos que la IA considera dudosos. Todos los
campos tienen una apariencia neutral porque una confianza baja no significa automáticamente que el dato sea
incorrecto: significa que una persona debe comprobarlo. Antes de guardar, la persona marca `He revisado todos
los datos de la factura.` y acepta la responsabilidad. Si queda algún bloqueo real, como un CIF de contraparte
inválido, el botón sigue desactivado pero ahora aparece una explicación concreta de lo que falta. Si se edita
un dato después de marcar la revisión, la casilla vuelve a quedar desmarcada.
La suite frontend queda en 441 tests.

### Revisión controlada, borrado seguro y duplicados (R-052, 27/08/2026)

Después de guardar una factura, la aplicación ya no salta sola a otra. Si quedan facturas listas para
revisar, pregunta si se quiere abrir la siguiente: **Sí** la abre y **No** vuelve a `Mis facturas`. Si no
queda ninguna, vuelve directamente a la bandeja.

Una factura que todavía no se ha confirmado se puede eliminar desde la bandeja o desde la pantalla de
revisión. Primero aparece una confirmación con el mensaje de que esa factura todavía no se ha confirmado ni
guardado. El servidor borra la fila y sus datos relacionados dentro de la base de datos, y después intenta
limpiar la imagen del almacén privado. Una factura confirmada no se puede borrar: el servidor lo rechaza.

La aplicación conserva dos defensas contra duplicados. Si la imagen es exactamente la misma, el hash SHA-256
evita crear otra fila y ofrece revisar la original o repetir la foto. Si la imagen cambia pero el OCR encuentra
el mismo número de factura, CIF propio, CIF de contraparte e importe, el documento se marca como duplicado y
no se puede guardar. Si coinciden número y ambos CIF pero falta o cambia el importe, se marca como sospecha y
también exige revisar la original o eliminar la nueva factura pendiente. El servidor repite esta comprobación
al confirmar para cubrir dos ventanas abiertas a la vez.

Para investigar la espera entre **Tomar foto** y **Usar foto**, el navegador registra marcas locales separadas
para capturar el frame, analizarlo, recortarlo/normalizarlo y mostrar la vista previa. No se guardan imágenes ni
datos fiscales en esas medidas. Además, OpenCV empieza a cargarse al abrir la cámara, no después de pulsar el
disparador. Falta medir el resultado con el PC concreto de Julio y repetirlo después en móvil.

La suite frontend queda en 446 tests. R-052 sigue en verificación manual de experiencia de usuario; la
validación backend sintética y el despliegue de staging ya pasan.

### Hotfix de captura cuando falla OpenCV (R-052, 27/08/2026)

Se reprodujo un problema real en el que la cámara capturaba el frame, pero cualquier fallo al analizarlo
con OpenCV hacía que la aplicación mostrara "No se pudo preparar la foto" y descartara la vista previa.
Ahora ese análisis es opcional: si OpenCV falla, se conserva la imagen completa y aparece **Usar foto**;
solo se pierde temporalmente la información opcional de nitidez y recorte. Se añadió un test de comportamiento
para impedir que vuelva a bloquear la captura. La suite frontend queda en 446 tests. El hotfix está desplegado
en staging; falta comprobarlo con el móvil real de Julio.

### Paleta clara del app shell (R-053, 27/08/2026)

Se cambió únicamente la paleta de colores del contenido autenticado: ahora el fondo es crema claro, las
superficies son blancas, el texto es oscuro y el acento naranja sigue respetando el tenant. La barra superior
continúa oscura y la cámara conserva su fondo oscuro para que la factura se vea bien. No se cambiaron botones,
textos, estructura, rutas ni funcionalidades. El cambio se aplica a usuarios, tenants y paneles de
administración con los permisos que ya tenían. La suite frontend queda en 446 tests y el despliegue de
staging está verificado; falta la revisión visual manual por cada rol.

### Rediseño Tinted Navy Liquid Glass (R-054, 28/08/2026)

Sobre la paleta clara se añadió un lenguaje visual nuevo, sin cambiar lo que la aplicación hace. El fondo de
las pantallas autenticadas es claro, las tablas, formularios, importes y listas usan superficies blancas para
que sigan siendo fáciles de leer, y la navegación superior, los botones principales y los diálogos usan un
azul marino profundo con borde cian, reflejo interior y sombra suave. Es el efecto llamado **Liquid Glass**,
pero tiene una versión opaca equivalente para navegadores que no permiten desenfocar el fondo.

La captura mantiene la misma pantalla y las mismas decisiones, incluido el selector de empresa cuando corresponde.
El visor de cámara continúa siendo oscuro para que la factura contraste, mientras que la previsualización vuelve
al lenguaje claro del resto de la aplicación. La bandeja, historial, confirmación y paneles tenant/platform
comparten los mismos colores, estados y controles visuales, pero conservan sus permisos y acciones originales.

También se dejaron visibles los focos de teclado y se prepararon estados para movimiento reducido, contraste
alto y forced colors. La suite frontend queda en 446 tests; typecheck, build y lint pasan. Falta la revisión
visual manual en móvil, escritorio y con cada rol antes de cerrar R-054.

### Ajuste del lenguaje glass en captura (R-054, 28/08/2026)

Tras probar el primer diseño en staging, se reforzó el fondo con halos azul/cian y naranja para que el efecto
glass se perciba de verdad. Las dos acciones principales, **Tomar foto** y **Subir archivo**, ahora forman una
fila de botones de igual altura; debajo quedan **Varias facturas** y **Varias hojas**, cada uno con un icono
que ayuda a reconocer su función. Ninguno usa una superficie blanca. **Recibida** y **Emitida** forman un único
selector segmentado y **Recibida** continúa siendo la opción inicial.

El color naranja del tenant se conserva, pero con degradado, transparencia, borde luminoso y reflejo interior
para integrarlo con el acabado glass. La nueva versión se ha reconstruido y publicado en staging; el health
público responde correctamente.

En un ajuste posterior se redujo aproximadamente un 20% el tamaño de todos los botones de captura. Las dos
opciones de varias facturas, **Varias facturas** y **Varias hojas**, permanecen siempre juntas en la misma fila,
incluido el móvil, usando texto e iconos compactos.

### Selector de captura y marca Autofactu (29/08/2026)

La pantalla para subir facturas ahora tiene un único bloque principal de dos botones pegados: **Tomar foto**
ocupa dos tercios y lleva un icono de cámara, mientras **Varias hojas** ocupa exactamente un tercio y lleva un
icono de páginas apiladas. Solo hay una línea divisoria entre ambos y las esquinas redondeadas pertenecen al
bloque completo, por lo que se comporta como una única pastilla. Las acciones menos frecuentes, como subir un
archivo o capturar varias facturas, siguen disponibles debajo.

También se sustituyó el logo por el de **Autofactu by Autoken** en el login y la cabecera. Se recortó el símbolo
original, sin las palabras de la derecha, y ese recorte se usa en el favicon y en los iconos de instalación de la
PWA. No se redibujó la marca: se reutilizó la imagen original y se prepararon los tamaños que necesita el móvil.
El frontend se reconstruyó y publicó en staging; las dos rutas de imagen responden ya como ficheros PNG reales,
no como una página antigua de la aplicación.

En una revisión posterior se tomó el azul dominante exacto del fondo del logo, `#021232`, y se aplicó al shell
superior, al panel glass de inicio de sesión, a los fondos navy de la aplicación y al color de la PWA. El fondo de
los recortes también se aplanó a ese color hasta las esquinas, incluido el icono cuadrado de instalación, para que
no aparezca un rectángulo de otro tono alrededor de la marca.

Después se redujo el símbolo dentro del icono PWA al 75% y se dejó un margen azul uniforme alrededor. De esta
forma el documento y el check quedan completamente visibles cuando el móvil aplica su propia máscara al icono.

En el último ajuste se redujo otro 15% y se amplió el margen para que el símbolo respire aún más. La unión entre
**Tomar foto** y **Varias hojas** ahora se hace con dos pastillas curvas solapadas, no con una línea recta. Se
intercambiaron **Subir archivo** y **Varias facturas**, dejando la subida de archivo en naranja. El enlace **Ver
historial** lleva al mismo panel **Mis facturas**; la ruta antigua se conserva solo como redirección para no romper
enlaces guardados. Finalmente se recuperó un acabado glass en la aplicación, usando transparencias, bordes y
sombras sobre el azul `#021232` y el naranja de marca.

En un ajuste posterior se hizo visible ese acabado en todas las pantallas: el fondo general ahora tiene
luces ambientales azul/cian y naranja, los paneles principales son translúcidos y tienen reflejo interior,
borde luminoso y sombra, y las acciones antiguas adoptan el mismo cristal azul marino. Las tablas, campos
de datos y la cámara siguen siendo superficies sólidas para que se puedan leer y usar correctamente.

### Integración final del logo y mejoras de acceso (29/08/2026)

El logo completo oficial de Autofactu que aparece en el login y en la barra superior ya no lleva un rectángulo
azul pegado a la imagen: sus píxeles de fondo son transparentes y dejan ver el azul glass de la superficie
donde se coloca. El favicon del navegador y los iconos cuadrados de instalación de la PWA usan, en cambio,
el símbolo con fondo azul completo, porque esos formatos necesitan una base propia y no muestran el lockup
completo con la palabra Autofactu.

En la pantalla de captura se eliminó el enlace redundante a **Ver historial**. Las facturas siguen quedando
guardadas y disponibles desde **Mis facturas**. En el login se añadió un ojo accesible para mostrar u ocultar
la contraseña; empieza siempre oculto, no borra lo escrito y funciona igual para cualquier rol.

Después se extendió el cristal al fondo completo del shell autenticado: ya no queda una zona blanca alrededor
de los paneles, sino una superficie navy continua con luces ambientales y paneles glass encima. El botón
**Tomar foto** conserva el naranja de marca. También se hizo más tolerante la apertura de cámara, con una
resolución compatible para PC y móvil, conexión explícita del stream al vídeo y reproducción reintentada
cuando el navegador informa de que ya puede mostrarlo.

### Cierre del ajuste de cámara y selector dividido (29/08/2026)

La cámara ahora usa una altura dinámica igual a la pantalla visible del dispositivo (`100dvh`) y evita que un
contenedor interno con altura mínima empuje los controles fuera del móvil. El vídeo sigue ocupando todo el fondo,
pero la barra inferior conserva siempre **Capturar foto**, **Subir archivo** y **Cerrar cámara** visibles.

El selector inicial de captura quedó como dos botones reales e independientes: **Tomar foto** delante, en naranja,
y **Varias hojas** detrás, con solape de 14 píxeles. El segundo botón tiene estado accesible para indicar cuándo el
modo multipágina está activo, y puede volver al modo simple antes de capturar. Se corrigió además la cascada CSS que
estaba aplicando por error el estilo glass genérico sobre estos botones.

La validación final pasó con **449 tests**, typecheck, lint sin errores y build de producción. El despliegue oficial
reconstruyó frontend, API y worker; los tres dominios públicos (`panel-staging.autoken.es`, `setex.autoken.es` e
`ilex.autoken.es`) respondieron correctamente y API/worker quedaron saludables. Falta únicamente la comprobación
manual con cámara física en móvil y escritorio, porque este entorno no tiene un navegador automatizado con permisos
de cámara.

### Cámara fullscreen sin recorte del panel glass (29/08/2026)

Se corrigió el último problema visual de la captura. El recuadro de la cámara y sus controles ya no se dibujan
dentro del panel glass de la pantalla: el overlay se coloca directamente en el cuerpo de la página. Esto evita que
el desenfoque y el recorte del panel padre reduzcan su altura aparente. El layout tiene ahora una zona flexible para
la imagen y una barra inferior independiente para los botones, respetando también la zona segura del móvil.

La nueva estructura quedó cubierta por un test de comportamiento y se volvió a publicar con el despliegue oficial.
La suite completa sigue en **449 tests verdes**, con typecheck y build correctos.

### Aplicación del tema Tinted Navy Liquid Glass (30/08/2026)

Se guardó en la raíz el prompt maestro `PROMPT-MAESTRO-REDISENO-FRONTEND-TINTED-NAVY-LIQUID-GLASS.md` y se
aplicó su primera integración real al frontend existente, sin reconstruir la aplicación ni tocar backend, base de
datos, API, permisos o lógica funcional.

El azul de marca no se aproximó a ojo: se inspeccionó `frontend/public/autofactu-favicon-solid.png`, cuyo fondo
uniforme dominante es `RGB(2, 18, 50)`, es decir, `#021232`. El lockup transparente `frontend/public/autofactu-logo.png`
es el logo oficial que usa la interfaz. Ese valor alimenta el token `--brand-navy` y las superficies de identidad.

La aplicación pasa a ser mayoritariamente clara: el shell y las pantallas de datos usan fondo y superficies blancas,
los formularios permanecen sólidos, y el navy se reserva para navegación, identidad, resumen y cristal destacado. Se
añadió un login con panel de marca separado del formulario, estados de foco visibles, fallback sin
`backdrop-filter`, opción de desactivar el efecto mediante `data-liquid-glass="off"` y reglas para movimiento reducido.

La integración conserva las rutas reales existentes: login, plataforma, ajustes, ranking OCR, laboratorio, pendientes,
facturas, empresas, mis facturas, captura, confirmación y supervisión. No existen rutas independientes de registro,
recuperación o activación de cuenta en este frontend.

La suite completa mantiene **449 tests verdes**, typecheck y build correctos. El lint no tiene errores y conserva solo
los dos avisos preexistentes de `SessionProvider.tsx`. El frontend se publicó mediante `infrastructure/deploy.sh` y
los hosts públicos respondieron correctamente. La comprobación visual en cada tamaño y navegador queda pendiente de
un navegador automatizado o una sesión manual con capturas reales.

### Selector de captura ampliado (30/08/2026)

El selector de captura se amplió al doble de altura, hasta **96 píxeles**, para que tenga una presencia más clara en
móvil y escritorio. **Tomar foto** ocupa el espacio principal y **Varias hojas** se convirtió en una pieza estrecha y
alta: su texto aparece en dos líneas y mantiene el nombre accesible completo para lectores de pantalla.

La pieza de varias hojas usa ahora un cristal claro translúcido con desenfoque, borde cian y el mismo solape visual
con el botón principal. Se mantuvo intacta la acción que abre el flujo multipágina. Los **449 tests** siguen verdes y
el ajuste quedó publicado con el despliegue oficial.

### Ajustes concretos del visor de captura (30/08/2026)

Se aplicaron los ajustes específicos del visor sin cambiar su funcionamiento. **Tomar foto** usa ahora un azul de acción
derivado de la marca, `--brand-action-blue` (`#164B82`), más luminoso que el navy estructural para no verse casi negro.
**Subir factura** y **Capturar foto** usan `--brand-orange`, cuyo valor extraído del color naranja uniforme del logo es
`#FD6702`; el texto usa navy para mantener contraste.

El título **Capturar factura** sigue existiendo como encabezado accesible, pero se oculta visualmente para eliminar el
espacio innecesario. La pantalla inicial ocupa toda la altura útil disponible, queda centrada en móvil y escritorio y
tiene un ancho máximo para no ocupar toda la pantalla. **Subir factura** y **Varias facturas** quedan apilados, uno debajo
de otro. El visor de cámara ya no muestra ningún botón de subida.

La linterna conserva su lógica y ahora se representa con un icono más reconocible de linterna, tamaño táctil mínimo y estados
`Activar linterna`/`Desactivar linterna` mediante `aria-label` y `aria-pressed`. Los controles **Cerrar cámara**,
**Automático** y **Manual** usan texto claro sobre el fondo oscuro del visor.

La investigación de marcos encontró que `camera-guide-frame` era un borde fijo decorativo del visor: no participaba en
recorte, OCR, detección ni coordenadas. `DocumentOverlay` es el SVG que calcula el tamaño, transforma las esquinas
detectadas y muestra la guía/feedback de detección. Se mantiene `DocumentOverlay` como único marco visible dominante,
conservando toda su lógica; el borde fijo queda estructuralmente presente pero sin borde para evitar la doble guía. La
guía base se amplió al 88% del ancho y al 80% del alto, acercándose a los bordes de la cámara.

La pantalla inicial usa una superficie glass translúcida con desenfoque, reflejo superior, borde claro y sombra. Los
iconos de instalación PWA conservan su diseño, pero ahora están centrados dentro de una envolvente un 5% menor con
esquinas redondeadas. El favicon por defecto usa la misma envolvente redondeada.

La suite frontend completa pasó con **449 tests**, typecheck, lint sin errores y build correcto. El despliegue oficial
reconstruyó la imagen del frontend y verificó los hosts públicos. El backend, la API, los endpoints, la subida global de
archivos y la infraestructura no se modificaron.

### Tema visual Tinted Navy Liquid Glass (31/08/2026)

Se alineó la capa visual común del frontend con la paleta exacta solicitada: navy `#021231`, naranja `#FA6703`, fondo
`#F4F7FB`, superficies `#FFFFFF`/`#F8FAFC`, textos `#101828`/`#667085` y bordes `#E4E7EC`. Las pantallas claras
siguen usando superficies sólidas para formularios, listados y datos fiscales; solo paneles, navegación, modales y
controles destacados reciben el cristal azul marino con desenfoque, borde, reflejo y sombra.

No se modificó backend, API, navegación, estructura JSX, orden, posición, tamaño estructural, eventos ni lógica de
cámara/OCR/subida. Se añadió únicamente acabado visual común, foco visible, fallback sólido del cristal y prevención de
scroll horizontal.

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

## 2026-08-31 - R-056: navegación y entradas de factura

El usuario tiene ahora cuatro accesos claros: Escáner, Subir Archivo, Pendientes e Historial. La pantalla de
subida acepta hasta diez imágenes o PDF independientes y si uno falla los demás siguen adelante. Pendientes
usa el inbox existente y avisa cuando hay diez documentos que requieren atención. Historial solo muestra
facturas confirmadas de los últimos cuatro meses y permite avanzar con un cursor, sin editar filas.

La dirección recibida/emitida ya no se presupone en el flujo de usuario. Hay que elegirla antes de capturar o
subir, y después de una subida la pantalla se limpia. El administrador mantiene su menú separado. El backend
identifica los PDF por sus bytes, los almacena sin tratarlos como imágenes y filtra el historial en la base de
datos por confirmación, fecha y propietario.

## 2026-09-01 - Ajustes de UI del flujo de usuario (9 pasos)

Retoques sobre lo construido en R-056, pedidos por Julio para que el flujo de usuario (Escáner, Subir
Archivo, Pendientes, Historial) se vea y se use mejor en el día a día:

- El menú de abajo ahora es el doble de alto, con un icono propio por destino (una lupa para el
  Escáner, una flecha hacia arriba para Subir Archivo, un triángulo de aviso para Pendientes, dos
  hojas para Historial) encima del nombre, y las esquinas de arriba redondeadas.
- El interruptor Recibida/Emitida del Escáner ya no está pegado arriba: ahora aparece justo encima
  de los botones de "Tomar foto", centrado en la pantalla.
- Se quitó una frase que sobraba bajo esos botones ("Para subir documentos independientes...").
- Las dos barras de navegación (arriba y abajo) ya no son blancas en modo claro: llevan un azul
  clarito de la marca, y el logo (que es blanco) va sobre un recuadro navy para que se siga viendo
  bien en los dos temas.
- El interruptor de tema ahora solo ofrece Claro/Oscuro (se quitó "Sistema" como opción visible,
  aunque por dentro se sigue respetando el tema del móvil/ordenador mientras la persona no elija).
- El icono de la linterna de la cámara es ahora una linterna de verdad (antes eran unos trazos que
  no se entendían).
- La pantalla de Subir Archivo ya no se ve "dentro de una tarjeta": el contenido flota sobre el
  fondo de la app, centrado.
- El Historial ahora muestra el número de cada factura (cuando existe) en vez de un genérico
  "Factura enviada", y se quitó el texto "Solo lectura" de cada fila. El número de factura ya vivía
  en la base de datos desde antes; solo hacía falta que el backend lo entregara y el frontend lo
  pintara.
- Pendientes ya no muestra las fotos que salieron ilegibles (esas ni se han llegado a leer, así que
  no tiene sentido pedir que se "compruebe" algo que no se pudo procesar). Se limpian solas a los 90
  días por el mismo mecanismo que ya limpiaba otros documentos sin confirmar; no hizo falta crear
  nada nuevo para eso.

Todo esto se hizo con tests que primero fallaban (describiendo el comportamiento nuevo) y luego se
puso el código mínimo para que pasaran, tanto en frontend como en el backend que hizo falta tocar
(número de factura e ilegibles). Al revisar la línea base del backend antes de tocar nada, aparecieron
4 tests de historial que ya fallaban de antes (piden documentos sin confirmar en el historial, algo que
R-056 cambió a "solo confirmadas" sin actualizar esos tests): no se tocaron por quedar fuera de este
encargo, pero quedan anotados para que Julio decida si se corrigen o se retiran.

**En cristiano:** "TDD" (a lo que se refiere el punto anterior) es escribir primero la prueba que
comprueba que algo funciona como se pide -y verla fallar a propósito, en rojo- antes de escribir el
código que lo hace funcionar. Sirve para no marcar algo como "hecho" solo porque compila: la prueba
demuestra que el comportamiento pedido existe de verdad, y se queda ahí para avisar si alguien lo
rompe sin querer en el futuro.

## 2026-09-02 - Ajustes de UI v3: Escáner, menú, Pendientes e Historial con filtro de periodo

Segunda ronda de retoques (encargo separado del anterior), sobre lo ya construido en los 9 pasos
del 2026-09-01:

- **Escáner:** en modo claro ya no aparece un recuadro oscuro flotando sobre el fondo (antes se
  veía un "bloque de cristal" navy encima de la pantalla blanca); en oscuro sigue igual que
  siempre. El botón "Tomar foto" pasa de navy a naranja de marca (con texto navy, para que se lea
  bien). El interruptor Recibida/Emitida usa ahora el mismo componente que Subir Archivo, en vez
  de uno propio. "Tomar foto" y "Varias hojas" eran antes dos mitades de un mismo botón pegadas
  (una encima solapaba a la otra); ahora son dos botones independientes, uno debajo del otro, con
  espacio de verdad entre ambos.
- **Menú de abajo:** la rayita naranja que marca en qué pantalla estás es un poco más gruesa y
  ahora se recorta bien dentro de las esquinas redondeadas de la barra (antes, en el primer o
  último icono, podía asomar por la curva).
- **Pendientes:** ya no se enseña el número de páginas de cada documento. El estado ("Pendiente de
  comprobación", etc.) ya no lleva una etiqueta con recuadro de color, solo el icono y el texto.
  "Revisar factura" tiene ahora un recuadro verde, "Eliminar" uno rojo, y "Ver progreso" uno gris
  neutro, todos con más espacio interior para que no se vean apretados. La tarjeta "Listas" del
  resumen de arriba desaparece (ese número se traslada al Historial).
- **Historial:** aparece un desplegable arriba (Total / Este mes / Este trimestre / Este año) que
  filtra las facturas por su propia fecha (no por cuándo se subieron), con el número de facturas
  que hay en ese periodo al lado. Cada fila muestra ahora, bien diferenciadas, tres cosas: el
  número de la factura, la fecha de la factura ("Fecha factura: ...") y la fecha en que se subió
  ("Subida: ..."). Si falta un dato, se dice "Sin número" o "Sin fecha", nunca se inventa nada.
  La hora de subida, tanto aquí como en Pendientes, ya no enseña los segundos (antes decía algo
  como "10:30:45", ahora solo "10:30").

Decisión técnica documentada: filtrar por "este trimestre" o "este mes" necesita saber en qué zona
horaria vive cada gestoría, pero el sistema todavía no guarda esa información por gestoría. Como
hoy todas las gestorías que usan la aplicación están en España, se ha fijado la hora de Madrid como
válida para todas, dejado anotado en el código que el día que haya una gestoría en otro país habrá
que añadir una zona horaria configurable de verdad.

Al revisar toda la batería de pruebas del backend (no solo lo tocado en este encargo) aparecieron
6 fallos que ya existían de antes, sin relación con este trabajo: 5 son pruebas de Historial
escritas antes de que se decidiera que solo enseña facturas ya confirmadas, y 1 es un aviso de que
falta una comprobación de seguridad (que una gestoría no pueda borrar un documento de otra) en un
botón de borrado que ya existía. Se dejan anotados para que Julio decida qué hacer con ellos, en
vez de tocarlos sin que los pidiera este encargo.

**En cristiano:** cuando el código pide la hora de "ahora mismo" a un ordenador, ese ordenador
tiene que decir también EN QUÉ ZONA HORARIA está esa hora (si no, "las 10 de la mañana" no
significa lo mismo en Madrid que en México). Aquí se ha fijado esa zona a "Europa/Madrid" de forma
fija en el código, en vez de preguntársela a cada gestoría, porque de momento todas están en el
mismo sitio. El día que eso cambie, habrá que guardar la zona horaria de cada gestoría en la base
de datos en vez de tenerla fija.

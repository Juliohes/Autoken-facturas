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

## 5. Qué queda por delante

- **Sprint 3** (en marcha): edición de una factura con registro de quién cambió qué (S3.3), gestión de
  empresas y usuarios desde el panel (S3.4), y marcar/purgar facturas de prueba (S3.5).
- **Sprint 4**: panel de la plataforma (dar de alta asesorías nuevas en minutos) y personalización visual
  por asesoría (cada una con su logo y colores).
- **Sprint 5**: refuerzo de seguridad y pruebas de carga antes de dar el paso final.
- **Fase de despliegue**: el día que Setex (la v1 actual) se apaga y todo el mundo pasa a usar esta versión
  nueva.
- **Ampliación decidida el 22/07/2026** (fuera del orden anterior, aún sin empezar a construir): mejorar
  automáticamente la foto de cada factura antes de leerla (más contraste/brillo) y comparar varios "lectores
  de IA" a la vez en todas las facturas durante unos días, para medir cuál lee mejor cada campo. Antes hace
  falta construir un interruptor (solo para Julio) que permita apagar este modo experimental sin tocar
  código, porque cuesta dinero real en llamadas a las IAs.

**Avance estimado hacia producción a día de hoy: ≈50%** (25 de 50 tareas del plan "core", sin contar el
módulo de Verifactu, la limpieza final del servidor viejo, ni la ampliación del 22/07 —aún no tiene número
de tarea fijo—, que van en paralelo y no bloquean el lanzamiento).

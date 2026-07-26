# CLAUDE.md — Resumen operativo Autoken Facturas v2

> Fuente de verdad: **`PLAN_MAESTRO_AUTOKEN_FACTURAS_V2_v1.2.md`**. Este archivo es un resumen de arranque
> para retomar contexto en cualquier sesión. Si hay conflicto, manda el PLAN MAESTRO.
> Se actualiza al cerrar cada tarea (sección "Estado actual").

---

## 1. Reglas de Oro (innegociables — sección 1 del plan)
1. **Supervisión**: Julio aprueba el plan de cada sprint antes de codificar. Dentro del sprint, autonomía tarea a tarea.
2. **Commits atómicos**: un commit por tarea con sus tests en verde. Jamás commits gigantes mezclando temas.
3. Nada se mergea a `develop` con CI en rojo. Nada a `main` sin tag de release.
4. **Anti-alucinación OCR**: campo no legible = `null` + aviso visual. Prohibido que un valor inventado llegue a la UI.
5. **Anti-cruce de tenants**: la suite de aislamiento (sección 8) es gate de CI bloqueante. Si falla, no se mergea.
6. **Sin secretos en el repo**: `.env` en `.gitignore` desde el commit 1; secretos por env vars + doppler/sops. Pre-commit `gitleaks`.
7. Staging nunca contiene datos reales de clientes.
8. **Código completo**: nunca `...` ni TODOs silenciosos. Pendiente → issue en GitHub.
9. Toda decisión arquitectónica → ADR en `docs/adr/NNN-titulo.md`.
10. **Idioma**: código e identificadores en inglés; comentarios de dominio, ADRs y docs en español.
11. **Registro único (Julio, 2026-06-14)**: TODO (decisiones, desvíos, hallazgos, ADRs, runbooks, issues) se
    documenta en el **PLAN MAESTRO** o enlazado desde su **§11 Registro central**. El plan es el sitio único;
    este `CLAUDE.md` es solo el resumen de arranque. Al cerrar cada tarea, actualizar §11 del plan.
12. **Commit + push por tarea (Julio, 2026-06-14)**: cada tarea deja **commit y `git push`** a GitHub (rama
    feature publicada + PR). En tareas largas, commits incrementales y push temprano para no perder trabajo.
13. **Comunicación con Julio (Julio, 2026-07-13)**: cada vez que se explique algo hecho, añadir **debajo** de
    la explicación técnica un bloque **"En cristiano (para quien no sabe de software)"** en lenguaje llano que
    enseñe los conceptos (endpoint, migración, RLS, test, middleware...). Julio aprende software con el
    proyecto. Además: **commit + push por feature**, **guardar/checkpoint cada tarea**, **nada de monolitos**
    y **revisar SOLID en todo** lo que se programa. No preguntar de más: continuar con autonomía; solo
    preguntar lo imprescindible (decisiones de dominio/producto que no se puedan resolver solo).
13-bis. **Guía en cristiano viva (Julio, 2026-07-22)**: `docs/GUIA_EN_CRISTIANO.md` es el registro
    permanente de qué hace la app y cómo está construida por dentro, explicado en lenguaje llano. **Al
    cerrar cada tarea/iteración** (spec aprobada, código en verde, PR mergeado), añadir ahí una entrada
    resumen en cristiano de lo construido (qué es, para qué sirve, sin jerga sin explicar). No es opcional
    ni se pregunta: se hace siempre, como el commit+push. Es distinto del `CLAUDE.md`/PLAN MAESTRO (que son
    la fuente técnica) y del bloque "En cristiano" de cada respuesta (que es efímero, de esa conversación);
    este archivo es el resumen acumulado y consultable de todo el proyecto.

## 2. Git y commits (sección 2 del plan)
- **Repo**: privado `Juliohes/Autoken-facturas` (monorepo: `backend/`, `frontend/`, `infrastructure/`, `docs/`).
- **Ramas**: `main` (prod, solo desde `release/*`+tag) · `develop` (integración, PR+CI verde) ·
  `feature/<ID>-<slug>` (una por tarea, se borra tras merge) · `release/vX.Y.Z` · `hotfix/vX.Y.Z+1`.
- **Flujo por tarea**: rama `feature/<ID>-<slug>` desde `develop` → implementación + tests → commit(s) atómicos →
  PR a `develop` con CI verde → merge → borrar rama.
- **Conventional Commits**: `tipo(ámbito): descripción` referenciando el ID. Ej.: `feat(tenancy): S1.1 modelo tenants con RLS forzado`.
  - Tipos: `feat fix refactor test docs chore ci perf security`.
  - Ámbitos: `tenancy identity intake ocr companies platform reporting frontend infra verifactu`.
- **Tags**: release `vX.Y.Z`; hito por sprint `sprint-N-done`; hito por fase `fase-0-done`.
- **Prohibido**: commit gigante multi-tarea, commits con tests rotos, push directo a `main`, force push, TODOs silenciosos.

## 9.1 Mapa de secretos (referencias, NUNCA valores en el repo)
| Secreto | Dónde vive |
|---|---|
| `AZURE_DOCINTEL_KEY` / `AZURE_DOCINTEL_ENDPOINT` | GitHub Secrets + `.env` del VPS |
| `AZURE_OPENAI_KEY` / `AZURE_OPENAI_ENDPOINT` | GitHub Secrets + `.env` del VPS |
| `MISTRAL_API_KEY` (solo POC) | GitHub Secrets + `.env` del VPS |
| `SMTP_HOST/USER/PASSWORD` (soporte@autoken.es) | GitHub Secrets + `.env` del VPS |
| `POSTGRES_PASSWORD`, `MINIO_KEYS`, `JWT_SECRET`, `DB_ENCRYPTION_MASTER_KEY` (S5.2, ADR-0018: clave por tenant derivada de esta, nunca guardada aparte) | Generados en el VPS, solo en `.env`/volúmenes cifrados |
| `BACKUP_ENCRYPTION_KEY`, `BACKUP_DATABASE_ADMIN_DSN`, `RESTORE_DRILL_TARGET_DSN` (S5.3, ADR-0019) | **NUNCA en el `.env` de `api`/`worker`** (ese fichero se monta entero en ambos contenedores, sin lista blanca) — fichero de entorno aparte, leído solo al invocar `scripts/backup_database.py`/`restore_drill.py` |
| Contraseñas de login Julio/Alberto | En ningún sitio: se crean en el primer login con 2FA |

## Infra (recordatorio crítico de seguridad)
- **VPS A `72.60.186.89`**: ejecuta la **v1 de Setex EN PRODUCCIÓN**. NO SE TOCA salvo el hardening de acceso de la tarea 0.3.
  Cualquier otro comando sobre esa máquina requiere autorización explícita previa de Julio en el chat.
- **VPS B `2.24.8.109`**: aquí se construye la v2 (staging durante el desarrollo, producción en go-live).
- Dominio: `autoken.es` (Cloudflare, `*.autoken.es` → VPS B). Subdominios de primer nivel (ADR-004).

---

## Estado actual (reconciliado 2026-07-24 — ver PLAN MAESTRO §11.11)
- **Fase real (git log)**: Sprint 1 (tenancy/identity/companies) completo. **Sprint 2 (intake+OCR)
  COMPLETO** (S2.2 cerrada 24/07/2026, PR #93 — verificación en hardware real pendiente). **Sprint 3
  (panel de asesoría) COMPLETO**: S3.1 (panel de facturas, PR #77), S3.2 (export Excel, PR #80), S3.3
  (edición auditada, PR #81), S3.4 (gestión de empresas/usuarios, PR #82) y S3.5 (facturas de prueba)
  cerrados y mergeados.
- **Sprint 4 (panel de plataforma) arrancado**: S4.1 (alta de tenant en minutos), S4.2 (theming
  runtime), S4.3 (manifest PWA dinámico), S4.4 (modo demo) y S4.5 (métricas y consumo) cerrados y
  mergeados. S4.1: primer endpoint del proyecto protegido por el rol `platform_admin` (antes solo
  servía para login); ver ADR-0013 (enmienda 2026-07-24). S4.2/S4.3: el frontend aplica el branding
  del tenant (logo/colores/nombre/favicon/manifest) solo en `App.tsx`/`index.html` (único punto de
  entrada hoy); retocar las pantallas ya construidas para que lo consuman queda para la tarea de
  app-shell. S4.4: `is_demo` en el alta + "Convertir a producción"/"Purgar" en el panel; la purga de
  un tenant demo es atómica en el propio SQL (`SELECT ... FOR UPDATE` + `DELETE`, migración 0011)
  tras un hallazgo de la auditoría (condición de carrera en el pre-chequeo original). S4.5:
  `GET /platform/tenants/metrics` (migración 0012, función `SECURITY DEFINER`
  `platform_tenant_metrics()`, mismo patrón `list_tenants`); "coste OCR acumulado" del CA no es
  construible hoy (no hay coste/tokens normalizados en `ocr_extractions` ni tabla de precios) —
  sustituido por `ocr_extractions_count`, nunca presentado como dinero (decisión de dominio
  documentada en la spec, no una desviación silenciosa). **S4.6 (dominios propios) cerrado con
  alcance acotado, decisión explícita de Julio tras preguntarle**: el mecanismo de aplicación (campo
  `custom_domain` asignable desde el panel + resolución de tenant por él, migraciones 0013/0014)
  está construido y probado con TDD contra Postgres real; el `Caddyfile`/TLS on-demand real y la
  verificación con un dominio de verdad apuntando a la VPS quedan **explícitamente pendientes** de
  una sesión futura con acceso a esa infraestructura (dominio ya reservado para esa prueba:
  `setex-facturas.autoken.es`, no `setex.autoken.es`, reservado para D.2). Auditoría: 2 hallazgos de
  arquitectura corregidos (validación no rechazaba un `custom_domain` reservado de plataforma, que
  nunca habría podido resolver; `convert_tenant_to_production` no devolvía el `custom_domain` real
  de un tenant demo que ya tuviera uno asignado), 1 de seguridad corregido (el fallback por dominio
  propio no tenía caché, abriendo una vía de amplificación de peticiones a Postgres vía `Host`
  arbitrario — se reutilizó la misma `NegativeTenantResolutionCache` que ya protege el subdominio,
  #52), y 1 bloqueante de cobertura corregido (el `revision` de la migración 0014 tenía 40
  caracteres, por encima del límite de `alembic_version.version_num` — habría roto `alembic upgrade
  head` en cualquier entorno; blindado con un test guardarraíl nuevo). En la verificación final se
  encontró y corrigió además una regresión real: cualquier `Host` de una sola etiqueta (sin punto,
  como el que usa el cliente de test o un healthcheck interno) generaba una consulta a Postgres sin
  ninguna posibilidad de resolver — descartado ahora antes de tocar la BD. **S4.7 (ciclo de vida
  tenant) cerrado y mergeado — SPRINT 4 COMPLETO**: `suspend_tenant`/`reactivate_tenant` (bloquean
  login al instante, sin tocar datos, reutilizando el mecanismo de `status` ya construido en
  S1.2/S1.6), `export_tenant` (ZIP con las 12 tablas del tenant vía `tenant_session` + ficheros de
  MinIO, sin función `SECURITY DEFINER` de lectura por tabla) y `delete_tenant` (a diferencia de
  `purge_demo_tenant`/S4.4, puede borrar un tenant REAL: exige `confirm_slug` exacto + un export
  previo, condición atómica en una única función SQL con `SELECT ... FOR UPDATE`, migración 0015).
  Auditoría de 3 perspectivas, especialmente rigurosa por ser la operación más peligrosa del
  proyecto hasta ahora: la función `delete_tenant` se confirmó correcta y atómica rama a rama (sin
  hallazgos de seguridad media/alta); sí se corrigió 1 bug real de comportamiento (`export_key_for`
  con precisión de segundo permitía que dos exports seguidos del mismo tenant se pisaran en
  silencio en MinIO — ahora lleva un sufijo `uuid4`) y se reforzó la cobertura (12 tablas del
  export, tenant suspendido, tenant demo por la vía general, atomicidad bajo dos `DELETE`
  concurrentes). El panel de plataforma (`PlatformTenants.tsx`) se refactorizó extrayendo
  `TenantRowActions`/`MutationErrorBanner` tras crecer demasiado con las acciones de S4.4+S4.7.
- **Hallazgo transversal (S3.4, 2026-07-23) → RESUELTO por S4.9 (2026-07-24)**: las pantallas de
  frontend construidas hasta ahora vivían y se probaban aisladas, sin login real ni menú ni routing
  que las conectara. **S4.9 (app-shell) cerrada**, primera tarea del lote de cierre de backlog
  previo al Sprint 5 (decidido con Julio): `SessionProvider` (contexto de sesión, `access_token` en
  memoria por ADR-0012, nunca persistido), `LoginScreen` (con segundo factor si aplica), middleware
  nuevo en `api/client.ts` (inyecta `Authorization`, intercepta un 401 con refresh-y-reintento vía
  `tokenStore`, deduplicando refresh concurrentes), `react-router-dom` (nueva dependencia) con rutas
  y menú por rol derivados de una única tabla (`app/routes.ts`). `App.tsx` sustituye por completo al
  placeholder de healthcheck de la Fase 0 (retirado, `api/health.ts` borrado por quedar sin uso).
  Auditoría de 3 perspectivas: 1 hallazgo **crítico** corregido (un rol desconocido/corrupto en
  `/auth/me` no invalidaba la sesión — dejaba al usuario atrapado en una pantalla en blanco con
  menú vacío en vez de devolverlo a login, tal y como exige la spec; ahora `SessionProvider` valida
  el rol contra un tipo cerrado antes de aceptar la identidad), 1 hallazgo **alto** de seguridad
  corregido (la caché de TanStack Query no se limpiaba al cerrar sesión — un segundo usuario en la
  misma pestaña podía ver brevemente datos del anterior; ahora `logout()` y el manejador de "no
  autorizado" comparten un único `endSession()` que también limpia la caché), y varios medios/bajos
  coincidentes en las tres lentes (guarda de `status==='loading'` que faltaba en la ruta de login,
  fuga menor en el `Map` de reintentos ante fallos de red sin `onError`, tabla rol->ruta duplicada
  entre el router y el menú, y `tokenStore` reubicado de `features/session/` a `api/` por dirección
  de dependencias) — todos corregidos.
- **S2.2 (captura guiada) cerrada y mergeada (PR #93) — SPRINT 2 COMPLETO** salvo verificación en
  hardware real: segunda tarea del lote de cierre de backlog. Nueva ruta `/capturar` (nuevo
  `ROLE_HOME.user`, antes `/historial`), 100% frontend, sin tocar `POST /uploads` (S2.1). Cámara
  trasera (`getUserMedia`) con fallback a selector de fichero nativo; auto-captura por frames
  (varianza del Laplaciano para nitidez + detección de contorno de 4 lados vía OpenCV.js para
  encuadre, ambas condiciones a la vez); recorte + corrección de perspectiva automáticos tras la
  captura, sin bloquear si no hay bordes claros; pantalla de revisión obligatoria antes de subir;
  selector Recibida/Emitida propagado a la confirmación (S2.4) vía `location.state`.
  `@techstark/opencv-js` cargado de forma perezosa (excluido del precache del service worker,
  `vite.config.ts`), probado contra el WASM real con imágenes de muestra generadas por código (no
  solo mockeado) — primera vez en el proyecto que se verifican así algoritmos de visión por
  ordenador. Auditoría de 3 perspectivas: 1 hallazgo **crítico** corregido (la auto-captura no
  propagaba el frame capturado desde el bucle de análisis hasta la pantalla de revisión — el botón
  "Usar esta foto" quedaba deshabilitado para siempre en ese camino, solo la captura manual
  funcionaba; corregido hilvanando el frame en el mismo callback que despacha la acción, con test
  de regresión dedicado), 2 hallazgos **altos** coincidentes en dos lentes corregidos (un fichero no
  decodificable como imagen en el fallback dejaba al usuario en un callejón sin salida silencioso;
  un `user` sin empresa asignada llegaba a ver la cámara en vez de un error temprano, spec §5), y
  varios medios/bajos corregidos (fuga de URLs de objeto sin revocar, decisiones de negocio
  extraídas a `captureSelectors.ts`, `useCompanyOptions` reubicado de `features/panel/` a
  `features/companies/` por cohesión, evento `ended` del stream de cámara). **Verificación en
  Android/iPhone real explícitamente pendiente** de una sesión futura con hardware (decisión de
  dominio confirmada por Julio, mismo patrón que la infraestructura de S4.6).
- **Hotfix (PR #94, mergeado 2026-07-24)**: `GET /auth/me` daba **401 siempre para `platform_admin`**
  (usaba `current_identity`, que exige un tenant resuelto por subdominio) — regresión real desde
  S4.9, que empezó a llamar `/auth/me` también tras el login de plataforma: el login del app-shell
  para `platform_admin` estaba roto en producción desde que se mergeó S4.9, sin detectarse porque
  los tests de frontend mockean el cliente API. Encontrado investigando el prerrequisito de S4.10 y
  reproducido de extremo a extremo contra el backend real antes de arreglarlo. Nueva función SQL
  `find_platform_admin_by_id` (migración 0016, mismo patrón `SECURITY DEFINER` que
  `find_platform_admin` por email del login), nueva dependencia `current_identity_for_me` (admite
  tenant y `platform_admin`), `MeOut.tenant` pasa a `str | null` (aditivo). Auditoría de 3
  perspectivas: **SEGURO/SOLIDO** en seguridad (0 hallazgos); 1 hallazgo alto corregido (fuga de
  cierre de sesión/transacción de BD en el camino de excepción de la nueva dependencia, un `async
  for` desnudo no propagaba el cierre al generador interno — corregido con `contextlib.aclosing`) y
  1 bajo corregido (mapeo de fila duplicado entre `read_identity`/`read_platform_identity`,
  extraído a un helper común).
- **S4.10 (interruptor admin-tech) cerrada — tercera y última tarea del lote de cierre de backlog previo
  al Sprint 5**: prerrequisito de S2.9/S2.10/S4.8 (decisión de Julio 2026-07-22), solo el mecanismo del
  interruptor, sin engancharlo todavía al pipeline OCR. `users.is_admin_tech` (migración 0017): flag sobre
  una cuenta `platform_admin` ya existente, nunca activable desde la aplicación (decisión de Julio: flag,
  no un rol nuevo en el enum cerrado) — `find_platform_admin_by_id` (0016) pasa a devolverlo también.
  `platform_settings`: tabla de una sola fila (mismo patrón `id boolean PK DEFAULT true CHECK(id)` que el
  resto de `platform_admin`) con el único ajuste, `ocr_experiment_enabled`, tras `GET/PUT
  /platform/settings` protegido por `require_admin_tech()` (exige `platform_admin` + el flag, comprobado
  fresco contra Postgres en cada petición — no embebido en el JWT, para que revocarlo en Postgres surta
  efecto al instante). `GET /auth/me` expone `is_admin_tech`. Frontend: ruta `/plataforma/ajustes` y
  enlace "Ajustes" en el menú condicional al flag (no solo al rol), pantalla con el interruptor sin estado
  optimista (activarlo dispara gasto real en cuanto lo lean S2.9/S2.10/S4.8). **Auditoría posterior (SOLID,
  3 hallazgos corregidos)**: `authz.py` consultaba la BD él mismo dentro de `require_admin_tech()`,
  mezclando "decidir según datos ya cargados" con "cargar esos datos" — la carga se extrajo a
  `current_admin_tech_identity()` en `identity/dependencies.py` (nuevo `AdminTechAuthContext`); la
  visibilidad del enlace "Ajustes" vivía en un `if` suelto de `Menu.tsx` en vez de en `ROUTE_DEFS`
  (`app/routes.ts`), reabriendo la duplicación rol->ruta que S4.9 ya había cerrado — se declaró como
  predicado `visible` junto al resto de la tabla; y la pantalla de ajustes lanzaba un GET que el backend
  iba a rechazar con 403 igualmente para quien no tiene el flag — ahora condicionado con `enabled`. Suite
  completa verificada en verde tras el refactor: 554 tests de backend + 184 de frontend.
- **S2.9+S2.10 (preprocesado de imagen + comparativa original-vs-realzada) cerradas — segunda pieza del
  lote de coste acotado tras S4.10**: `ocr/preprocess/enhance.py` (S2.9, Pillow `ImageEnhance`
  contraste/brillo/saturación, parámetros conservadores sin afinar contra el bench real — eso exige
  llamadas de pago, spec §6) + `ocr/comparison.py`/`ocr/comparison_repository.py`/tabla
  `ocr_comparison_runs` (S2.10, migración 0018, RLS de dos niveles igual que `ocr_extractions`):
  compara la lectura original vs la realzada puntuando con el MISMO `ocr.analysis.analyze_invoice`
  que ya usa producción (reutilizado, no reinventado); empate exacto -> `tie`, nunca un ganador
  inventado. Enganchada a `jobs.ocr.run_ocr` (`run_ocr_comparison`) en su PROPIA transacción, tras la
  principal ya confirmada: un fallo de la comparativa nunca toca el resultado real. Todo detrás de
  `platform_settings.ocr_experiment_enabled` (S4.10), **apagado por defecto** — coste cero hasta que
  Julio lo active. Backfill retroactivo construido (`jobs/ocr_backfill.py` + función `SECURITY
  DEFINER` `ocr_backfill_candidates()` + CLI `scripts/backfill_ocr_comparison.py`), probado solo en
  modo simulación: la ejecución real dispara llamadas de pago sobre el histórico completo y queda
  pendiente de que Julio la autorice, igual que activar el interruptor de verdad. **Auditoría en 3
  lentes (SOLID, arquitectura, patrones+seguridad), 2 hallazgos altos coincidentes en dos lentes + 2
  hallazgos altos de seguridad de la tercera, todos corregidos antes de cerrar**: `ocr/backfill.py`
  invertía la dirección de dependencias `jobs->ocr` (importaba de `jobs.ocr`) — movido a
  `jobs/ocr_backfill.py`; el camino en vivo pedía la lectura "original" DOS veces al lector (una en
  `run_ocr`, otra dentro de la comparativa), triplicando en vez de doblando el coste real por factura
  — corregido pasando la lectura ya calculada como parámetro opcional; sin tope de dimensiones antes
  de decodificar con Pillow bytes no confiables (riesgo de decompression bomb, cualquier tenant podía
  subir una imagen adversarial) — `ImageTooLargeError`, tope 40M píxeles, chequeado antes de `.load()`;
  el realce (CPU/memoria) corría síncrono sobre el event loop compartido del worker arq, congelando el
  OCR de TODOS los tenants por un solo fichero — envuelto en `asyncio.to_thread`, igual que la
  descarga de MinIO. También varias duplicaciones (DRY): `serialize_tax_lines` compartida
  (`ocr/extraction.py`), constante `ENHANCED_CONTENT_TYPE` compartida, claves de `validations` como
  constantes en `ocr/analysis.py`, filtro de content-types soportados movido de SQL a Python (fuente
  única de verdad), `GRANT SELECT` a nivel de columna en vez de tabla completa, aislamiento de fallos
  por candidato en el backfill real. 554 tests de backend previos + 20 nuevos, todos en verde.
- **S4.8 (panel de ranking multi-modelo) cerrada (PR #98) — última tarea del lote de cierre de backlog
  previo al Sprint 5, LOTE COMPLETO**: alcance completo decidido explícitamente por Julio (los 6 motores,
  no un MVP de 2) — Gemini 3 Flash/Pro, Claude Vertex, gpt-5.1, Azure DocIntel (`prebuilt-invoice`) y
  Mistral OCR4 leyendo la misma factura, puntuados con el mismo `ocr.analysis.analyze_invoice` que ya usa
  producción. Extractores estructurados nuevos para los 5 motores que no lo tenían (Gemini ya lo tenía de
  la Fase 1): prompt/parseo JSON compartido (`ocr/extraction_json.py`) para los promptables (Claude,
  gpt-5.1), mapeo del esquema propio de Azure DocIntel, Mistral siempre con campos vacíos por diseño de su
  API (OCR puro, no promptable — asimetría documentada en la spec §0 y en el propio panel del frontend, no
  solo en el código). `ocr_ranking_entries` (migración 0019, RLS de dos niveles, N filas por fichero — una
  por motor, no columnas fijas) + función `SECURITY DEFINER` `ocr_ranking_summary()` (mismo patrón que
  `platform_tenant_metrics`) para el agregado cruzando tenants del panel; enganchado a `jobs.ocr.run_ocr`
  detrás del mismo interruptor de S4.10; backfill retroactivo propio; `GET /platform/ocr-ranking` protegido
  por `require_admin_tech()`; pantalla `OcrRanking.tsx` (motor / facturas leídas / puntuación media / primer
  puesto, empate a puntuación máxima cuenta para todos los empatados).

  **Incidente de seguridad real durante el desarrollo, divulgado a Julio en su momento**: un test con el
  interruptor de S4.10 encendido llamó al worker sin inyectar los motores del ranking; el código construyó
  los 6 extractores reales desde la config del entorno (que en este sandbox de desarrollo SÍ tiene
  credenciales reales configuradas), disparando llamadas de pago reales a los 6 proveedores con una imagen
  sintética. **Corregido de raíz, no solo parcheado**: `jobs.ocr_ranking.run_ocr_ranking` ya no tiene NINGÚN
  fallback interno a motores reales (su parámetro `extractors` es obligatorio); el único punto de
  producción legítimo que construye motores reales desde `.env` es `jobs.ocr.run_ocr`; el wrapper de test
  (`tests/_ocr.py::run_ocr`) exige `ranking_extractors` explícito, sin default — se auditaron y corrigieron
  los ~30 sitios de llamada afectados. Verificado además con la suite completa bajo
  `-W error::DeprecationWarning` (habría fallado si se importase cualquier SDK de proveedor real). La
  auditoría de 3 lentes (SOLID, arquitectura, patrones+seguridad) encontró **de forma independiente** un
  segundo bug de coste real: el motor por defecto (Gemini Flash) se llamaba DOS veces por factura (una para
  el resultado principal, otra para el ranking) — el mismo bug de coste duplicado que ya se había corregido
  en S2.10, reintroducido aquí; corregido reutilizando la lectura ya calculada (`default_reading`) en vez de
  repetir la llamada. Resto de hallazgos corregidos: test de agregación del panel que faltaba (spec §7 C11,
  multi-tenant, empates, aislamiento entre tenants), `serialize_reading` reubicado de `ocr/comparison.py` a
  `ocr/scoring.py` por cohesión, mapeo de Azure DocIntel movido dentro de su propio `try/except`, docstring
  incorrecto sobre manejo de PDF multi-página en el extractor de gpt-5.1. 623 tests de backend + 191 de
  frontend, todos en verde.
- **LOTE DE CIERRE DE BACKLOG PREVIO AL SPRINT 5 — COMPLETO (2026-07-25)**: las 5 tareas (S4.9 app-shell,
  S2.2 captura guiada, S4.10 interruptor admin-tech, S2.9/S2.10 realce+comparativa, S4.8 ranking
  multi-modelo) cerradas y mergeadas.
- **SPRINT 5 (hardening+QA) COMPLETO (25-26/07/2026)**: orden acordado con Julio por dependencias — S5.1 →
  S5.6 → S5.2 → S5.4 → S5.5 → S5.3. Julio autorizó continuar el sprint completo sin aprobar cada spec,
  avisando solo al final o si hacía falta su decisión/acceso real (mismo patrón que el lote de backlog
  anterior); ese fue el único caso real, S5.3 (ver detalle más abajo).
- **S5.1 (cabeceras y límites) cerrada (PR #100) — primera tarea del Sprint 5**: añade `Cross-Origin-Opener-
  Policy`/`Cross-Origin-Resource-Policy` (`same-origin`) a la base de cabeceras ya existente desde S1.6. El
  escaneo real con Mozilla Observatory queda **pendiente de un despliegue público** (no hay ninguno
  accesible desde este entorno de trabajo, mismo patrón que Caddy real de S4.6). Rate-limit por primera vez
  en dos endpoints sin protección: `POST /auth/activate/confirm` (fuerza bruta del TOTP de 6 dígitos al
  confirmar la activación, límite por token) y `POST /auth/refresh` (abuso de rotación, límite por IP) —
  reutiliza el patrón atómico ya existente de `identity/ratelimit.py` (script Lua INCR+EXPIRE, S1.3/S1.4).
  **Auditoría de 3 lentes: 0 críticos/altos, 6 medios/bajos, todos corregidos**: DRY (4 funciones nuevas de
  `ratelimit.py` extraídas a dos primitivas genéricas); arquitectura (el rate-limit de refresh vivía dentro
  de `sessions.rotate_refresh_token`, mezclando la invariante de rotación con una política transversal —
  extraído a un nuevo caso de uso `service.refresh_session`, simétrico a `authenticate`); un oráculo de
  enumeración real (un token de activación desconocido no contaba como fallo, así que un `429` solo ocurría
  contra un token válido, revelando su existencia — corregido, cualquier intento fallido cuenta ahora); un
  riesgo de DoS a usuarios legítimos (el contador de refresh por IP no se reseteaba en éxito, así que
  usuarios detrás de una IP compartida podían arrastrar fallos ajenos hasta el bloqueo — corregido, se
  resetea tras una rotación exitosa); cabeceras ausentes en la respuesta `413` del middleware de tamaño de
  petición (es el más externo a propósito, nunca pasaba por `SecurityHeadersMiddleware` — corregido,
  aplica el mismo conjunto directamente). 631 tests de backend en verde.
- **S5.6 (monitorización y alertas) cerrada (PR #102) — segunda tarea del Sprint 5**: decisiones de infra
  confirmadas por Julio (§0 de la spec): stack self-hosted en la VPS B, no SaaS; Sentry integrado pero
  apagado hasta que Julio cree la cuenta. Captura de errores opcional (`shared/error_tracking.py`, solo con
  `SENTRY_DSN`, `send_default_pii=False`/`max_request_body_size="never"` explícitos), `GET
  /api/v1/metrics` (`jobs/metrics_router.py`, formato Prometheus: contador HTTP por método+código vía
  `MetricsMiddleware` + salud de la cola OCR de arq vía `jobs/monitoring.py`, API pública `queued_jobs()`
  sin reconstruir claves de Redis a mano) — público a propósito, solo agregados operativos, añadido a las
  listas de rutas públicas de RBAC/aislamiento de tenants. Infraestructura como código completa en
  `infrastructure/`: Prometheus (scrape + reglas de alerta: caída de la API, tasa de 5xx, cola OCR
  atascada >10 min, disco <10%), Alertmanager (receptor `null` hasta que Julio decida el canal real),
  Grafana (datasource + dashboard básico), validados con `docker compose config`/`promtool check
  config`+`check rules`/`amtool check-config` reales (vía Docker). **Desplegar de verdad el stack contra la
  VPS B queda pendiente de una sesión futura con ese acceso** (mismo patrón que el Caddy/TLS real de S4.6;
  runbook en `docs/runbooks/observabilidad.md`). **Auditoría de 3 lentes: 1 ALTO + 6 medios/bajos, todos
  corregidos**: DoS de cardinalidad (el método HTTP se etiquetaba tal cual en el contador Prometheus; un
  atacante podía mandar métodos arbitrarios y agotar memoria del proceso con series nuevas sin límite —
  corregido con lista blanca de métodos conocidos, el resto se agrupa en "OTHER"); inversión de
  dependencias (`shared/metrics.py` importaba de `jobs.monitoring`; movido el endpoint agregador a
  `jobs/metrics_router.py`, `shared` deja solo la primitiva transversal); amplificación (`/metrics`
  público abría/cerraba un pool de Redis por petición sin límite de frecuencia — cacheado con TTL de 10s);
  fail-open de infraestructura (`GRAFANA_ADMIN_PASSWORD` con default `admin`; puertos de
  Prometheus/Alertmanager/Grafana en todas las interfaces sin autenticación propia — corregido: contraseña
  obligatoria + puertos en loopback); `uid` del datasource de Grafana ausente (el dashboard habría
  quedado en blanco en el primer despliegue real); docstring engañoso sobre una dimensión de "ruta" nunca
  implementada; imágenes `:latest` fijadas a versión. 638 tests de backend en verde.
- **S5.2 (cifrado por tenant) cerrada (PR #104) — tercera tarea del Sprint 5**: cifrado en reposo
  (pgcrypto `pgp_sym_encrypt`/`pgp_sym_decrypt`, ADR-0018) del CIF/NIF y nombre de empresas y
  contrapartes: `companies.cif/name`, `counterparties.cif/name`,
  `invoices.counterparty_tax_id/counterparty_name` (+ índice ciego, spec C5) y
  `ocr_extractions.counterparty_tax_id/counterparty_name`. Clave por tenant derivada con HKDF a
  partir de una única clave maestra (`DB_ENCRYPTION_MASTER_KEY`, nunca guardada en Postgres); clave
  de índice ciego DISTINTA de la de cifrado (HMAC-SHA256 determinista del CIF normalizado, único
  campo con índice — spec §0, decisión de Julio). Migración 0020 con backfill del histórico,
  validada empíricamente contra Postgres real. **Decisión de Julio tras preguntarle**: alcance
  "ampliado" (CIF + nombre, no solo CIF) con mecanismo pgcrypto (no Fernet); y, al descubrirse que
  cifrar el nombre rompía la búsqueda de texto libre del panel de facturas (S3.1), mantener el
  cifrado real y retirarla, sustituida por un filtro exacto de CIF vía índice ciego. El export de
  tenant (S4.7) sigue siendo legible (descifra antes de volcar a JSON); `invoice_edits` cifra
  condicionalmente `old_value`/`new_value` cuando el campo editado es sensible (C7). Script de
  rotación de la clave maestra (`jobs/key_rotation.py` + `scripts/rotate_encryption_key.py`) y su
  runbook (`docs/runbooks/rotacion-clave-cifrado.md`); no ejecutado contra datos reales (solo hace
  falta ante sospecha de filtración).

  **Auditoría de 3 lentes, la más exhaustiva del proyecto hasta ahora dado el riesgo (crítico real,
  no solo teórico, en 4 de los hallazgos)**: (1) los 4 modelos ORM (`Company`, `Counterparty`,
  `Invoice`, `OcrExtraction`) no se habían actualizado tras la migración 0020 — `alembic check`
  **fallaba de verdad** (verificado ejecutándolo), arriesgando que un futuro `--autogenerate`
  revirtiera el cifrado; corregido y reverificado en verde. (2) el engine no ocultaba los
  parámetros de las sentencias SQL (`hide_parameters=True`, ahora en `shared/db.py`): cualquier
  excepción sobre una consulta cifrada filtraba la clave del tenant en claro en logs/Sentry. (3)
  faltaba `normalize_tax_id` antes del índice ciego en el backfill y en la rotación para
  `invoices` (única tabla no pre-canonicalizada): rompía en silencio el filtro exacto de CIF tras
  migrar o rotar. (4) condición de carrera real en la rotación de clave (una fila insertada durante
  la ventana de rotación podía quedar indescifrable para siempre) — mitigada con `SELECT ... FOR
  UPDATE` por tabla + el runbook ahora exige parar la app durante la rotación; al implementarlo
  salió a la luz un quinto bug real independiente: `invoice_edits` es append-only (solo `SELECT,
  INSERT` concedidos desde S3.3) y la rotación de sus valores sensibles fallaba con `permission
  denied` — migración 0021 concede `UPDATE` acotado a las dos columnas de ciphertext, sin tocar el
  resto de la fila (sigue siendo inmutable de verdad), cubierto con un test de regresión dedicado.
  Además: routers derivando la clave directamente en vez de vía servicio (incluido el propio módulo
  de referencia, `companies/router.py`); lógica de derivación de clave/índice reimplementada en 5
  sitios, extraída a `shared/encryption.py`; `--new-master-key` por CLI (visible en `ps`) retirado,
  solo env var. **Hallazgo fuera de alcance, documentado no corregido**: `ocr_comparison_runs`/
  `ocr_ranking_entries` (S2.9/S2.10/S4.8, experimento apagado por defecto) guardan el CIF/nombre de
  contraparte en claro dentro de una columna JSONB — decisión pendiente de Julio antes de activar
  el experimento en producción. 655 tests de backend + 191 de frontend, todos en verde.

  **Incidente de transparencia divulgado a Julio en su momento**: validar `docker compose config`
  (tarea de S5.6, no de esta) había impreso claves reales de Azure/Mistral del `.env` real en la
  conversación de trabajo; sin llamada externa alguna, pero se recomendó rotarlas por precaución.
- **S5.4 (pentest básico propio) cerrada (PR #106) — cuarta tarea del Sprint 5**: checklist OWASP Top 10
  del plan maestro (IDOR, inyección, auth, uploads) ejecutada como pentest ADVERSARIAL de caja negra
  contra la app real (Postgres/Redis/MinIO reales, nunca mocks), no como revisión de código. Antes de
  escribir un test se hizo reconocimiento completo de la superficie de ataque y de la suite ya
  existente: inyección SQL (sin vector real, todo parametrizado, revisado sistemáticamente), uploads
  (`test_intake_upload.py` ya exhaustivo: bytes reales no cabecera, tamaño, ClamAV real, fail-closed) e
  IDOR (`test_tenant_isolation.py`, barrido sistemático con guardarraíl de cobertura) ya tenían
  cobertura de sobra — documentado en la spec §0, no repetido. Huecos reales identificados y cubiertos
  con tests nuevos (`tests/test_pentest_s5_4.py`, C1-C7b): tokens JWT construidos a mano contra
  `/auth/me` (`alg: none` sin firma, confusión de tipo `refresh`/`access`, firma con secreto distinto,
  expirado); condición de carrera REAL (`asyncio.gather`, no secuencial) en la rotación de refresh,
  confirmando que exactamente una de dos rotaciones simultáneas con la misma cookie triunfa; dos
  tenants importando el mismo CIF sin colisión en el índice ciego por tenant (S5.2) ni cruce de datos;
  confirmación ligera de que metacaracteres SQL clásicos se tratan como texto literal. **Resultado real
  del pentest: las 8 pruebas pasan sin necesitar ningún cambio de código de producción** — cada defensa
  ya construida en tareas anteriores (gracias a las auditorías de 3 lentes de cada tarea previa)
  resistió el ataque tal cual estaba. Sin auditoría de 3 lentes propia (no hay código de producción
  nuevo que auditar, solo tests). 663 tests de backend en verde (655 previos + 8 nuevos).
- **S5.5 (pruebas de carga) cerrada (PR #108) — quinta tarea del Sprint 5**: prueba de carga real con k6
  (50 subidas concurrentes contra `POST /uploads`, Postgres/Redis/MinIO reales de este entorno de trabajo,
  sin ningún worker `arq` arrancado — el intake nunca dispara coste real de IA). **Hallazgo real, no
  teórico**: con los valores por defecto de SQLAlchemy (`pool_size=5`, `max_overflow=10`, 15 conexiones
  simultáneas como máximo), 43 de 50 peticiones fallaban con `QueuePool limit... timeout 30.00` y p95 de
  ~32s, porque cada subida retiene una conexión durante varias consultas secuenciales (comprobación de
  membership, insert). Corregido haciendo `db_pool_size`/`db_max_overflow` configurables
  (`shared/config.py`, default 20/20, sin hardcodear en `shared/db.py`) y **verificado empíricamente con un
  segundo run de k6 tras el fix**: 0 fallos de 50, p95 = 2.59s. Durante la verificación, una corrida
  intermedia mostró 43/50 éxito y 7 "fallos" que resultaron ser `409 duplicate_of` (deduplicación por
  sha256 funcionando correctamente contra ficheros ya subidos en la corrida original, antes del fix) — se
  investigó el cuerpo real de la respuesta antes de concluir nada, para no confundir un artefacto de test
  con una regresión. Sin auditoría de 3 lentes propia (cambio de configuración acotado, sin lógica de
  dominio nueva). 663 tests de backend en verde. Herramientas del load test (k6, guion `upload_test.js`,
  ficheros JPEG generados) no versionadas en el repo (fuera de alcance de la spec, herramienta puntual).
- **S5.3 (backups + restore drill) cerrada (PR #110) — sexta y última tarea del Sprint 5, SPRINT 5
  COMPLETO**. Decisión de alcance confirmada por Julio antes de codificar (spec §0, preguntado
  explícitamente al no haber credenciales de Hetzner en este entorno): construir el mecanismo completo
  y verificarlo empíricamente contra Postgres real, dejando el cron nocturno real en la VPS y la subida
  a un destino externo real pendientes de una sesión futura con esas credenciales (mismo patrón que
  S4.6/S5.6). Backup completo (`pg_dump --format=custom`) cifrado en memoria con AES-256-GCM
  (`BACKUP_ENCRYPTION_KEY`, ADR-0019 — secreto DISTINTO de `DB_ENCRYPTION_MASTER_KEY` de S5.2: protegen
  modelos de amenaza distintos, rotar uno no afecta al otro) y escrito de forma atómica; restore drill
  que exige una base de datos destino completamente vacía y verifica recuento de filas + columnas
  cifradas byte a byte. **Verificado empíricamente, no solo en teoría** (mismo criterio que S5.5): 0.35s/
  86KB de backup y 1.10s de restore con 20 tenants sembrados (`docs/runbooks/backups-restore.md`).

  **Auditoría de 3 lentes con 2 hallazgos altos, uno coincidente en las 3**: (1) el DSN admin (con
  contraseña de superusuario bypass-RLS) se pasaba como argumento posicional a `pg_dump`/`pg_restore`,
  visible en `ps`/`/proc/<pid>/cmdline` mientras el proceso vive — exactamente el riesgo que la propia
  spec exigía evitar para `BACKUP_ENCRYPTION_KEY` pero no se había aplicado al DSN; corregido pasando la
  contraseña vía `PGPASSWORD` en el entorno del subproceso (`shared/pg_dsn.py`, nuevo). (2) la lente de
  seguridad encontró, de forma independiente, algo que las otras dos no vieron: `backup_encryption_key`
  era un `model_validator` global de `Settings` (mismo patrón que `jwt_secret`/`db_encryption_master_key`)
  — pero a diferencia de esos dos, ningún endpoint de la API ni el worker usan nunca ese secreto; al ser
  global, obligaba a inyectarlo también en su entorno compartido (`docker-compose.yml` monta el `.env`
  entero, sin lista blanca, en `api` y `worker`), deshaciendo el aislamiento de secretos que es la razón
  de ser de la propia ADR-0019 que esta tarea acababa de escribir. Corregido: `require_strong_
  backup_encryption_key()` es una función normal, llamada solo desde los dos scripts CLI que de verdad
  la usan. Resto de hallazgos corregidos: `postgresql-client` horneado en la misma imagen Docker que
  sirve tráfico HTTP público (corregido con un target `ops` separado en el `Dockerfile`, verificado con
  builds reales de ambos targets — `api` sin `pg_dump`, `ops` con él); el chequeo de "base de datos
  vacía" del restore drill solo miraba el schema `public` (corregido, todos los schemas de usuario);
  escritura atómica del backup con nombre de fichero temporal determinista, no único (dos ejecuciones
  solapadas del cron podían pisarse — corregido con sufijo `uuid4`, mismo patrón que `export_key_for` de
  S4.7); patrón subprocess duplicado sin timeout ni logging estructurado entre `jobs/backup.py` y
  `jobs/restore_drill.py` (extraído a `shared/subprocess_utils.py`, `structlog` añadido a ambos,
  consistente con el resto de jobs del proyecto). 683 tests de backend en verde (676 previos + 7 nuevos).
- **SPRINT 5 (hardening+QA) COMPLETO (2026-07-26)**: las 6 tareas (S5.1 cabeceras y límites, S5.6
  monitorización, S5.2 cifrado por tenant, S5.4 pentest propio, S5.5 pruebas de carga, S5.3 backups)
  cerradas y mergeadas, en el orden acordado con Julio. Quedan pendientes de infraestructura real (no
  bloquean el roadmap, documentadas cada una en su tarea): TLS real de dominios propios (S4.6), despliegue
  real del stack de observabilidad (S5.6), y el cron+destino externo real de backups (S5.3).
- **Guía en cristiano viva**: `docs/GUIA_EN_CRISTIANO.md` (regla 13-bis) ya mergeada; se actualiza al cerrar
  cada tarea.
- **Nuevas tareas decididas por Julio 2026-07-22 (detalle en plan §11.11)**:
  - **Kimi K3 aparcado**: servidores en Singapur, sin DPA/SCC — incumple la decisión ya cerrada de residencia
    UE (§11.7). Candidatos alternativos investigados: **dots.ocr** (autoalojable, resuelve RGPD de raíz),
    Qwen2.5-VL 72B, InternVL3 76B.
  - **Formato IVA sin ".0"/",0" superfluo**: implementado (`percentage.ts`, PR #78).

---

## Estado histórico (previo a la reconciliación — Fase 0)
- **Fase**: FASE 0 — Fundación.
- **Tarea cerrada**: **0.1 Repo GitHub** ✅ — repo privado `Juliohes/Autoken-facturas` creado; default branch
  `develop`; `main` y `develop` protegidas (PR obligatorio, sin force-push/borrado, historial lineal,
  conversaciones resueltas, reglas aplicadas a admins); README, .gitignore (.env excluido), estructura del
  monorepo, plantillas PR/issues, pre-commit gitleaks (verificado: *no leaks found*).
  > Las *required status checks* de CI se enlazarán en 0.6 cuando exista el pipeline.
- **Tarea cerrada**: **0.2 DNS de `autoken.es`** ✅ — DNS gestionado en **Hostinger** durante el desarrollo
  (no Cloudflare; ADR-0008, enmienda a ADR-004). Caddy hará el HTTPS. 5 registros A creados y **verificados**
  resolviendo a `2.24.8.109` (TTL 300): `setex`, `panel`, **`tuti`** (tenant demo, renombrado por Julio desde
  el provisional `joseramon`), `setex-staging`, `panel-staging`. Cloudflare: issue #2 (revisar antes del go-live).
- **Tarea cerrada**: **0.3 Hardening VPS** ✅ — acceso por clave SSH dedicada `autoken_deploy`.
  **VPS B `2.24.8.109` completo**: usuario `deploy` (sudo+clave), SSH solo clave (`AllowUsers deploy`),
  UFW 22/80/443, fail2ban, unattended-upgrades, root rotada (solo en VPS), Docker 29 + Compose.
  **VPS A `72.60.186.89` MÍNIMO** (ADR-0009): solo `PasswordAuthentication no`; NO se tocan usuarios/UFW/root.
  Decisión: construir todo en VPS B y retirar A tras migración (ver [[no-tocar-vps-a]]). Runbook:
  `docs/runbooks/provisioning.md`. Hallazgos informativos en A: puerto 2222 expone SSH del contenedor prod;
  staging de v1 corre en prod (no se tocan).
- **Tarea cerrada**: **0.4 Esqueleto backend** ✅ (PR #8) — FastAPI en Docker, `/api/v1/health`, structlog
  + correlation id, pydantic-settings, Alembic. Tests verdes; ruff/mypy OK.
- **Tarea cerrada**: **0.5 Esqueleto frontend** ✅ — React 18 + Vite + TS + Tailwind + PWA (manifest + SW);
  cliente API **autogenerado** desde el OpenAPI del backend (openapi-typescript + openapi-fetch) consultando
  `/api/v1/health` con TanStack Query. Build/typecheck/lint OK; E2E proxy verificado.
- **Tarea cerrada**: **0.6 CI completo** ✅ (PR #11) — GitHub Actions: backend (ruff/mypy/pytest), gate
  aislamiento, frontend (typecheck/lint/build), secretos (gitleaks) + audits, build imagen. Los 5 checks son
  **required** (strict, también admins) en `develop`/`main`: ningún PR mergea con CI en rojo.
- **Tarea cerrada**: **0.7 ADRs 0001-0006** ✅ — documentadas las decisiones cerradas (RLS 2 niveles, PWA→TWA,
  pipeline OCR, dominio/subdominios, Hostinger/Docker vs AWS, edición recibidas vs inmutabilidad emitidas).
- **Nota**: el proyecto vive en **`/opt/app-facturas/`** (no en `/opt`). Clave SSH en `~/.ssh/autoken_deploy`.
  Toolchain del entorno: Python 3.12 + venv en `backend/.venv`; **Node 20** + npm; Docker 29.
- **FASE 0 COMPLETADA** → tag `fase-0-done`. **STOP**: esperando aprobación de Julio antes de la Fase 1
  (POC OCR). La Fase 1 necesita entregables de Julio (cuentas Azure/Mistral + facturas reales).

### Pendientes de Julio (sección 9 del plan)
- [x] Autenticación GitHub para Claude Code (hecha vía `gh auth login`).
- [x] **0.2**: 5 registros A en hPanel de Hostinger creados y verificados (tenant demo = `tuti`).
- [x] **0.3**: acceso SSH entregado; VPS B endurecido completo, VPS A mínimo.
- **Fase 1 — candidatos OCR (rev. 2026-06-16, ver plan §11.7 + ADR-0007/0010)**: bench de Azure DocIntel (✅) +
  **Gemini 3 Flash/Pro** + **Claude** (Opus 4.8/Sonnet 4.6 vía Vertex UE, misma cuenta Google) + familia GPT en
  Azure (**`gpt-5.1`**; `gpt-4.1`/`gpt-4o` deprecados) + **Mistral OCR** + **PaddleOCR-VL** y **Qwen3-VL**
  self-hosted (los monta Claude Code). Cuentas que necesita Julio: 3 (Azure ✓, Google Cloud ✓, Mistral ✓). Capa de verificación "tipo DNI"
  (CIF/NIF mód-23, IBAN mód-97, VIES/AEAT, cuadre aritmético) común a todos → **implementada** en
  `backend/src/ocr/verification.py` (PR `feature/adr0010-verification-tipo-dni`, 26 tests verdes).
- **Entregables Fase 1 (estado 2026-06-30): TODO LISTO** (detalle en plan **§11.10**). Azure DocIntel
  (`autoken-docintel-we`, WE) ✓; Azure OpenAI (`autoken-openai-sweden`, Sweden Central) con **`gpt-5.1`
  desplegado** en Data Zone Standard (NUNCA Global) ✓ — `gpt-4.1`/`gpt-4o` quedaron **deprecados por Azure**
  (§11.3); Mistral `MISTRAL_API_KEY` ✓; **Google Vertex** proyecto `autoken-ocr` habilitado + facturación +
  SA `vertex-bench` (JSON en `secrets/vertex-sa.json`), región `europe-west4`, Gemini 3 y Claude (Opus
  4.8/4.7, Sonnet 4.6, Fable 5) disponibles ✓. **20 facturas** en `entregas/facturas/` ✓ → bench (1.2)
  desbloqueado. PaddleOCR-VL/Qwen3-VL los monta Claude Code.
- [ ] Pendiente de Julio (NO bloquea 1.2): prompt para integrar el **nuevo OCR de Mistral** como candidato del
      bench; SMTP soporte@autoken.es; Excel 51 empresas → `entregas/`.

### Enmienda 2026-06-18 — CIF de contraparte (plan §11.8, ADR-0011)
- **Identidad propia conocida**: el nombre/CIF de la empresa del usuario NO se leen por OCR; se inyectan desde
  `companies`. El OCR concentra el esfuerzo en **fecha + importes + CIF de la CONTRAPARTE** (lo que más falla).
- **Verificación del CIF de contraparte en 4 niveles**: L1 estructura (`ocr/verification.py`, ya hecho) · L2
  supplier master del tenant (`counterparties`) · L3 resolución externa (AEAT censal con certificado / VIES /
  BORME LibreBOR-OpenMercantil / eInforma-Axesor de pago) · L4 caché (`cif_lookups`). CIF inválido o inexistente
  → bloquea "Confirmar y guardar"; nombre que no casa → aviso con razón social oficial.
- **Pantalla de revisión**: siempre visibles total + CIF contraparte + fecha; el resto plegado; aviso rojo
  grande de responsabilidad bajo el botón. Implementación en tarea **S2.8** (+ refuerzos S2.3/S2.4).
- **Pendientes de Julio**: certificado electrónico para AEAT censal; decidir si se contrata API comercial de pago.

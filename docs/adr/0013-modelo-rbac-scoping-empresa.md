# ADR-0013: Modelo RBAC (portero de roles + scoping por empresa según rol)

- **Estado**: aceptado
- **Fecha**: 2026-07-08
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: PLAN MAESTRO §1 (regla de oro 5, aislamiento) y §3 (identidad),
  spec `docs/specs/S1.6-rbac.md`, ADR-0001 (RLS de dos niveles: `tenant_id` + `company_id`),
  ADR-0012 (estrategia de sesión/auth), ADR-0004 (subdominios). Cierra el issue #53.

## Contexto

S1.3 (ADR-0012) responde **quién** hace la petición (identidad) y a **qué asesoría** pertenece
(subdominio), y abre `tenant_session` para que la RLS de tenant sea efectiva. Faltaba responder **qué
puede hacer cada rol** y **hasta dónde ve los datos** dentro de la asesoría:

- La regla de oro 5 (aislamiento) no termina en la frontera del tenant: un empleado (`user`) ve
  **solo su empresa**, mientras que el administrador de la asesoría (`tenant_admin`) ve **todo su
  tenant**. Ese segundo nivel de la RLS (`app.company_id`) existía en el esquema (ADR-0001, S1.1)
  pero S1.3 lo dejó sin cablear.
- Los endpoints de negocio necesitan una forma **reutilizable y a prueba de olvidos** de declarar
  qué roles los pueden invocar (denegar por defecto).
- El `platform_admin` (Julio/Alberto) no pertenece a ninguna asesoría y opera desde `panel`; su
  login solo debe aceptarse en ese host (issue #53), no en cualquier host no-tenant.

## Decisión

**1. Portero de roles (`identity/authz.py::require_roles`).** Una dependencia construida sobre
`current_identity` (S1.3): si el rol de la identidad no está entre los permitidos del endpoint,
responde **403**. El **401** (no autenticado) lo da `current_identity` **antes**, de modo que la
autenticación siempre se comprueba antes que la autorización (prioridad 401 sobre 403). Los roles se
declaran con el enum `tenancy.constants.Role`, nunca con literales sueltos. **Denegar por defecto**:
una ruta de negocio sin portero se considera un olvido y el guard C10 la detecta.

**2. Scoping por `company_id` resuelto por petición (no en el token).** `current_identity` fija el
nivel de empresa de la RLS según el rol, sin que ese valor viaje en el JWT (así un cambio de
membership surte efecto sin reemitir tokens):

- `user`: se resuelve su **única empresa activa** vía `memberships`. Como la membership se necesita
  antes de conocer la empresa, se hace una lectura en **contexto de asesoría** (`app.company_id` sin
  fijar) para hallarla y luego se abre la sesión de trabajo acotada con `app.company_id` = esa
  empresa. La frontera "solo ve su empresa" la hace cumplir la RLS de Postgres (S1.1), no solo el
  código.
- `tenant_admin`: sin `app.company_id` (contexto de asesoría): ve todas las empresas del tenant. El
  rol manda sobre la pertenencia: aunque tuviera memberships, no se le acota.
- `platform_admin`: en un subdominio de tenant su `tenant_id` nulo no casa el subdominio -> 403
  (S1.3 C11). El acceso cross-tenant con audit log es S4 (fuera de alcance).

El mapeo rol -> contexto RLS es una **allowlist explícita** (`identity/scoping.py::scope_for_role`):
`user` -> contexto de empresa, `tenant_admin` -> contexto de asesoría, y **cualquier otro rol se
deniega (403)**. Nunca se concede visibilidad amplia por defecto a un rol no contemplado (denegar por
defecto también en el scoping, no solo en el portero). Aunque el CHECK de `users` restringe hoy los
roles a este conjunto, la allowlist evita que un rol futuro (o un token manipulado que pasara la
firma) obtenga contexto de asesoría por la rama `else` (endurecimiento de auditoría S1.6 A2).

**3. Invariante 1-A estricta (una empresa por empleado).** Un `user` necesita **siempre exactamente
una** empresa activa. Si resuelve a **0 o a más de una**, la cuenta está mal configurada: **403**,
sin servir datos (nunca un dato ambiguo), con **independencia de si la asesoría tiene otras
empresas**. En el mundo real un empleado nace con su empresa (S1.4); un empleado sin empresa es un
error de configuración, no un estado transitorio válido. El caso multiempresa (selector / unión de
varias) queda aplazado a un issue de seguimiento.

**4. Login de plataforma acotado a `panel` (cierra #53).** El login de un `platform_admin` solo se
acepta cuando el host es el de plataforma (`panel` / `panel-staging`). En cualquier otro host
no-tenant el camino a `platform_admin` (`find_platform_admin`, SECURITY DEFINER) ni siquiera se
intenta: el login devuelve un **401 neutro**, como una credencial inexistente (anti-enumeración). La
clasificación del host vive en `tenancy/resolution.is_platform_host` y la fija el middleware en
`request.state.is_platform_host`; el login de usuarios de tenant no cambia.

**5. Superficie de prueba: `GET /api/v1/companies`.** Endpoint de **solo lectura** (nuevo módulo
`companies/`) restringido a `tenant_admin` por `require_roles`; qué empresas devuelve lo decide la
RLS según el contexto. Es la superficie mínima para verificar la matriz; el CRUD/import de empresas
es S1.5.

## Consecuencias

- `current_identity` sigue siendo el **único** punto que fija `app.tenant_id`/`app.company_id` (vía
  `tenant_session`): el aislamiento no se dispersa. Un `user` genera dos sesiones por petición (una
  breve de asesoría para resolver la empresa + la de trabajo acotada); coste asumible para una
  garantía que hace cumplir la BD.
- Cada endpoint de negocio futuro **debe** declarar sus roles con `require_roles`; el guard C10
  enumera las rutas montadas y falla si una ruta de negocio queda sin proteger.
- El guard C10 enumera las rutas a partir del **esquema OpenAPI** (`app.openapi()["paths"]`), que
  lista paths y métodos en cualquier versión de FastAPI. Es robusto frente a cambios internos de
  `app.routes` (p. ej. la inclusión perezosa de routers de FastAPI 0.137), de modo que `fastapi` no
  necesita quedar fijado a una versión antigua.

## Alternativas descartadas

- **Meter la empresa en el JWT**: acoplaría el scoping a la vida del token (un cambio de membership
  no surtiría efecto hasta reemitir) y ampliaría la superficie si el token se filtra. Se resuelve por
  petición.
- **Aceptar el login de plataforma en cualquier host no-tenant**: filtra la existencia del
  `platform_admin` fuera de `panel` y amplía la superficie de ataque. Acotado a `panel` (#53).
- **Un framework de permisos (Casbin/OSO)**: sobredimensionado para tres roles y una matriz pequeña;
  un portero de dependencia + la RLS de Postgres cubren el caso con menos piezas.

## Enmienda (2026-07-24, S4.1): primer endpoint de negocio de `platform_admin`

La decisión 5 de este ADR dejaba explícitamente fuera de alcance "el acceso cross-tenant [de
`platform_admin`] con audit log... es S4". S4.1 ("Alta de tenant en minutos") lo abre: el primer
endpoint de negocio (no solo login) que un `platform_admin` puede usar (`POST`/`GET
/platform/tenants`). Esto introduce una **excepción explícita** a la regla dura de S1.2/S1.3 ("el
**token identifica**, el **subdominio aísla**"): para este rol, el JWT firmado con
`role = platform_admin` **es** la barrera completa, con independencia del host por el que llegue la
petición.

- **Por qué es seguro sin atar al host**: el login de `platform_admin` SÍ sigue atado a `panel`/
  `panel-staging` (decisión 4, sin cambios); una vez emitido el token, viaja por
  `Authorization: Bearer` (no por cookie, no hay CSRF), y la API no tiene CORS abierto. Comprobar
  además el host en cada petición autenticada no añadiría una frontera de confianza real (el `Host`
  lo controla el cliente), solo complejidad.
- **Mecanismo, no acoplado a `current_identity`**: una dependencia paralela,
  `identity.dependencies.current_platform_identity`, valida el JWT y exige el rol, sin depender de
  que el subdominio resuelva a un tenant (un `platform_admin` no tiene uno). Usa una sesión de BD
  sin RLS de tenant (`shared.db.platform_session`), y el acceso a `tenants`/`tenant_branding` pasa
  por funciones `SECURITY DEFINER` acotadas (`create_tenant`/`list_tenants`, migración 0010), mismo
  patrón que `resolve_tenant`/`find_platform_admin` (S1.2/S1.3): el rol runtime de la API nunca gana
  `SELECT`/`INSERT` directo y sin acotar sobre esas tablas.
- **Guard anti-olvido (C10) preservado**: `identity.authz.require_platform_admin()` envuelve
  `current_platform_identity` con el mismo `ROLES_MARKER` que `require_roles`, para que el guard que
  detecta endpoints de negocio sin portero (spec S1.6 C10) reconozca también este camino.
- **Traza de auditoría**: pendiente para cuando haya una operación que lo justifique (S4.1 es alta
  únicamente, sin modificar/borrar); se revisará en S4.7 (ciclo de vida del tenant: suspender/
  exportar/borrar), que sí son operaciones sensibles sobre asesorías ya existentes.

Este patrón (rol de plataforma como barrera completa, sin dependencia del host, vía
`current_platform_identity`/`require_platform_admin`/`platform_session`) es el que reutilizará el
resto de endpoints de plataforma de Sprint 4, no una excepción puntual de S4.1.

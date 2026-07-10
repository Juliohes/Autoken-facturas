# ADR-0014: Modelo de dos roles de BD con enforcement NOBYPASSRLS en arranque

- **Estado**: aceptado
- **Fecha**: 2026-07-10
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: ADR-0001 (RLS de dos niveles), PLAN MAESTRO §3.3, §8; issues #50, #52

## Contexto
El aislamiento multi-tenant de la plataforma (ADR-0001) descansa por completo en la Row-Level
Security de Postgres. La RLS solo aplica si la app se conecta con un rol que **no** puede eludirla.
Postgres deja saltarse la RLS a: (a) los superusuarios, (b) los roles con el atributo `BYPASSRLS`,
y (c) el **owner** de una tabla frente a `ENABLE ROW LEVEL SECURITY` (por eso la migración usa
`FORCE ROW LEVEL SECURITY`, que también obliga al owner).

Existen por tanto dos responsabilidades de BD claramente distintas:

1. **Owner / migraciones**: crea y altera el esquema, define políticas RLS y concede privilegios.
   Necesita privilegios elevados (incluido `BYPASSRLS` para poder sembrar y operar el esquema).
2. **Runtime de la app**: ejecuta las consultas de cada petición. Debe ser un rol **restringido**
   (`NOSUPERUSER`, `NOBYPASSRLS`, no-owner de las tablas) para que la RLS le aplique siempre.

La migración `0001` ya crea el rol runtime `autoken_app` con esos atributos. Pero nada impedía, por
un error de despliegue (un `DATABASE_URL` apuntando al superusuario, o un `GRANT`/`ALTER ROLE`
que concediera `BYPASSRLS`), que la app **acabara conectándose con privilegios elevados**. Ese fallo
es el más grave posible aquí —anula el aislamiento entre asesorías— y es **invisible** en
funcionamiento normal: todo "funciona", solo que sin fronteras.

## Decisión
Se formaliza el **modelo de dos roles** y se añade un **guardarraíl de arranque** que verifica el
invariante contra la conexión REAL de la app:

- Módulo dedicado `shared/db_security.py` con
  `assert_runtime_role_cannot_bypass_rls(engine)`, que consulta
  `SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user` y **lanza**
  (`RuntimeRoleCanBypassRlsError`) si el rol es superusuario o tiene `BYPASSRLS`, o si no se puede
  determinar (fail-closed).
- Se cablea en el **lifespan** de `main.py` **solo en producción** (`settings.is_production`): si el
  invariante no se cumple, la app **no levanta** (fail-loud, regla de oro 8). No se exige conexión a
  BD en dev/test, donde el arranque no debe depender de Postgres.
- Un test determinista (`tests/test_db_security.py`, marcado `isolation`) usa los dos DSN de test:
  con el del superusuario la aserción falla; con el del rol runtime restringido pasa.

### Parte de despliegue (fuera del código)
El guardarraíl comprueba el invariante, pero la garantía completa exige que el despliegue real:
- Ejecute las **migraciones** con el rol owner (con privilegios), y
- Configure `DATABASE_URL` de la app con el rol **`autoken_app`** (runtime, restringido), nunca con
  el superusuario ni con un rol al que se haya concedido `BYPASSRLS`.

## Decisión relacionada (#52): caché de resolución de subdominio, solo negativa
`resolve_tenant(slug)` consulta la BD en cada petición, incluso no autenticada, lo que abre un vector
de **DoS** (martilleo de subdominios) y **enumeración** por temporización pre-auth. Se añade una
caché (`tenancy/resolution_cache.py`, adaptador sobre `resolve_tenant`) con TTL corto y cota LRU que
**solo cachea el veredicto negativo** (slug que no resuelve):

- Es justo el patrón del ataque (slugs inexistentes probados en masa); cachear "no resuelve" elimina
  la carga de BD de las repeticiones sin revelar nada.
- Los resultados **positivos NO se cachean**, a propósito: así la **suspensión de un tenant surte
  efecto al instante** (invariante C23 de S1.3, revocación inmediata), sin ventana de staleness en
  la autorización. La única staleness es benigna y acotada por el TTL: un tenant recién **creado**
  puede tardar hasta `subdomain_cache_ttl_seconds` en empezar a resolver.
- Compromiso asumido: al no cachear positivos, un tenant real consulta la BD cada vez, lo que deja un
  canal de temporización teórico (existente = más lento que inexistente-cacheado). Es débil (la
  consulta es una función indexada `SECURITY DEFINER`, sub-milisegundo, ahogada por el jitter de
  red) y se acepta frente al requisito duro de revocación instantánea.

Settings nuevas: `subdomain_cache_ttl_seconds` (30) y `subdomain_cache_max_size` (1024).

### Alcance de la caché frente al DoS de alta cardinalidad (bajo, aceptado)
La caché negativa mitiga el **martilleo de subdominios repetidos** (el mismo puñado de slugs
inexistentes probados en masa): tras el primer fallo, las repeticiones se sirven de memoria sin
tocar la BD. **No** cubre el **spray de alta cardinalidad** (un slug único distinto por petición):
cada slug nuevo es un fallo de caché que llega a la BD, y con cota LRU los positivos de un ataque así
ni siquiera se retienen. Se decide **no** defender ese vector en el hot-path de la app: hacerlo
exigiría un rate-limit por IP contra un almacén compartido (Redis) en **cada** petición pre-auth,
metiendo una llamada de red en el camino más caliente y sin autenticar, justo lo que la caché en
memoria evita. La mitigación correcta vive en el **borde** (reverse proxy / Caddy) con rate-limit por
IP antes de que la petición llegue a la app. Queda como **tarea de infra** (no de código de la app);
riesgo residual **bajo** y **aceptado** hasta entonces.

## Alternativas consideradas
- **No verificar y confiar en el despliegue**: un `DATABASE_URL` mal configurado rompería el
  aislamiento en silencio. Inaceptable para el control de seguridad más crítico.
- **Verificar en cada petición**: coste innecesario; el rol de conexión no cambia en caliente. Un
  chequeo de arranque es suficiente y de coste despreciable.
- **Cachear también los positivos (TTL corto)**: cerraría del todo el canal de temporización, pero
  introduce una ventana en la que un tenant suspendido seguiría resolviendo, rompiendo la revocación
  instantánea (C23). Se descarta: la revocación inmediata pesa más que un canal de temporización
  débil.

## Consecuencias
- (+) Un despliegue que conecte la app con privilegios elevados **no arranca** en producción, en vez
  de operar con el aislamiento anulado.
- (+) La resolución de subdominio deja de ser un vector de DoS/enumeración barato para slugs
  inexistentes, sin sacrificar la revocación instantánea de tenants.
- (−) El despliegue debe mantener separados el rol de migraciones (owner) y el de runtime; el ADR lo
  documenta como requisito operativo.
- (−) Un tenant recién creado puede tardar hasta el TTL (segundos) en empezar a resolver; aceptable.

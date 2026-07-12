# ADR-0011: Verificación del CIF de la contraparte (fuentes, orden y caché global)

- **Estado**: aceptado
- **Fecha**: 2026-07-12
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: ADR-0010 (verificación "tipo DNI", L1), ADR-0001 (RLS de dos niveles), ADR-0014
  (rol runtime NOBYPASSRLS + guard de arranque), ADR-0016 (el worker OCR marca, el humano confirma);
  spec `docs/specs/S2.8-verificacion-cif-contraparte.md`; PLAN MAESTRO §11.8

## Contexto

El **CIF de la contraparte** (proveedor en factura recibida, cliente en emitida) es el campo que más
falla en el OCR y el más crítico contablemente. S2.3 ya lo **extrae** y valida su **estructura** (L1,
mód-23; ADR-0010). Falta responder lo que un humano no puede contestar de memoria: **¿este CIF existe
de verdad y su razón social es la que dice la factura?**

Verificarlo online tiene tres tensiones: (1) **coste/cuota/latencia** de las fuentes externas, (2)
**disponibilidad** (los servicios públicos, sobre todo VIES, se caen a menudo) y (3) **aislamiento
multi-tenant** (ADR-0001): qué datos pueden compartirse entre asesorías y cuáles no.

## Decisión

### Cuatro niveles, de barato/rápido a caro/autoritativo

Se verifica en orden y se corta en cuanto hay veredicto suficiente:

1. **L1 · Estructura** (`shared/tax_id`, ADR-0010): mód-23. KO -> `invalid` (bloquea), sin gastar
   cuota en basura ni cachear.
2. **L2 · Supplier master del tenant** (`counterparties`): CIF<->razón social ya confirmados por un
   humano de esa asesoría. Gratis, mejora con el uso, corta antes de tocar la red. **Por tenant**.
3. **L3 · Resolución externa**, en el orden de las fuentes habilitadas:
   - **AEAT censal** (VNifV2, SOAP mutual-TLS con certificado): **autoritativa** del par CIF+nombre.
     Su "no identificado" es determinante -> `not_found` (bloquea).
   - **VIES** (`checkVatApprox`, SOAP público): determinante **solo** para contrapartes intra-UE
     dadas de alta en el ROI. Su "no válido" para un CIF nacional **no** invalida. Como L1
     (`validate_tax_id`) solo admite identificadores **españoles**, el CIF que llega a VIES es siempre
     nacional y se consulta con `countryCode="ES"`; un `exists=True` para un ES es un `valid` legítimo
     (operador en el ROI). **La verificación de contrapartes intra-UE NO españolas queda DIFERIDA**:
     requeriría que L1 aceptara el formato VAT-UE (país + número) para no bloquear antes de llegar a
     VIES. No se implementa código de país extranjero "por si acaso" (sería código muerto).
   - **BORME** (OpenMercantil/LibreBOR, HTTP público): enriquece CIF->razón social de **sociedades**;
     no cubre autónomos ni es autoritativo.
   - **eInforma/Axesor (de pago): diferido** (solo si las gratuitas no cubren; comparar precios antes).
4. **L4 · Caché** (`cif_lookups`): antes de llamar a una fuente se consulta la caché; si hay entrada
   vigente (TTL no vencido) se usa sin llamar.

**Veredicto** (`CounterpartyVerdict`): `valid` (+`name_match` bool), `invalid`, `not_found`,
`unverified`. `valid`+`name_match=false` es **aviso** con la razón social oficial (no bloquea por el
nombre); la validación **marca, no inventa** (nunca corrige el CIF leído).

### Regla de oro de disponibilidad

**La caída/timeout de un tercero produce `unverified` (revisar manual), jamás `invalid`/`not_found`.**
Una factura no se bloquea por la indisponibilidad de un servicio externo. Un fallo de red **no** se
cachea como "no existe" (solo se cachean respuestas afirmativas de la fuente).

### Caché global `cif_lookups` (excepción deliberada a la RLS de dos niveles)

`cif_lookups` es **GLOBAL**: sin `tenant_id` y **sin RLS de tenant**. La razón social oficial de un
CIF en un registro **público** es la misma para todos y **no es dato de negocio de ninguna asesoría**;
compartir la caché ahorra cuota y latencia sin cruzar información. Guarda solo datos públicos (`cif`,
`source`, `exists`, `official_name`, `raw_json`, `fetched_at`, `expires_at`), único por `(cif,
source)`. Es una excepción **acotada y documentada** a la RLS de dos niveles (ADR-0001): la frontera
de tenant se mantiene intacta en todo lo que sí es dato de negocio.

El **supplier master (`counterparties`), en cambio, NO se comparte**: va con RLS `FORCE` por
`tenant_id` (patrón de `companies`/0001). Lo que una asesoría confía vale solo para ella (que una
asesoría confíe un CIF no hace que otra lo confíe).

**`raw_json` se guarda `{}` por diseño** (refuerza el aislamiento): aunque el esquema de `cif_lookups`
tiene la columna `raw_json`, `ResolutionResult` **no** transporta el payload crudo de la fuente y el
servicio persiste siempre `{}`. Es deliberado: guardar la respuesta cruda podría arrastrar a la caché
**global** un eco del `name_read` que aportó un tenant concreto (el matching aproximado de AEAT/VIES
recibe el nombre leído), y ese dato sí es del tenant. Con `raw_json = {}` la caché contiene solo el
hecho público `(cif, source, exists, official_name)`, nunca entrada de un tenant. (Enmienda explícita
a la spec §2, que listaba `raw_json` como si fuera a poblarse.)

### Requisito para S2.4: el `tenant_id` viene del principal autenticado

`verify_counterparty(tenant_id, ...)` y `record_confirmation(tenant_id, ...)` **confían** en el
`tenant_id` recibido para abrir `tenant_session` (que fija `app.tenant_id` y con él la RLS). **S2.4
DEBE derivar ese `tenant_id` del principal autenticado (el token de sesión), NUNCA de input del
cliente** (query/body/cabecera manipulables). La RLS de `tenant_session` es el backstop de defensa en
profundidad, pero la primera línea es no dejar que el llamante elija el tenant. Requisito de la capa
HTTP de S2.4.

### Interacción con el guard de aislamiento (ADR-0014) — no se debilita nada

El guard de arranque (`shared/db_security.py`) marca las tablas con RLS **habilitada pero sin FORCE**;
una tabla **sin RLS** como `cif_lookups` **no** lo activa. El guard dinámico C8 de `test_tenancy_rls`
solo exige RLS a las tablas con columna `tenant_id`, que `cif_lookups` **no** tiene. Por tanto **no
hace falta ninguna allowlist ni relajar el guard**: `cif_lookups` es pública global por diseño y el
aislamiento de las tablas de tenant (incluida la nueva `counterparties`) sigue verificándose igual.

### Feature flags por tenant

Columna `tenants.cif_sources` (JSONB, nullable): qué fuentes usa cada asesoría. `null` = conjunto por
defecto `["supplier_master", "aeat", "vies", "borme"]`. Permite, p. ej., una asesoría solo con
supplier master (sin llamadas externas -> `unverified` si no está en su master).

## Alternativas consideradas

- **Cachear por tenant** (`cif_lookups` con `tenant_id`): descartado. Multiplicaría llamadas y cuota
  para el mismo dato público sin ganar aislamiento (no hay dato de negocio que aislar).
- **Bloquear ante fuente caída**: descartado por la regla de disponibilidad (bloquearía facturas por
  un fallo ajeno). Se degrada a `unverified` (revisar manual).
- **Contratar ya eInforma/Axesor**: diferido; las fuentes gratuitas (AEAT autoritativa + VIES + BORME)
  cubren el caso general. Se evaluará coste solo si hace falta.
- **Fiar el par CIF+nombre a VIES/BORME**: descartado; no son autoritativos para lo nacional. AEAT
  censal es la única autoritativa del par.

## Consecuencias

- **Positivas**: veredicto estructurado para S2.4 (bloquea inválido/inexistente, avisa nombre que no
  casa); coste/latencia mínimos (L2 gratis, L4 evita repetir); disponibilidad > completitud (nunca se
  bloquea por un tercero); el supplier master mejora con el uso y queda aislado por tenant.
- **A vigilar**: la caché global asume que `cif_lookups` **nunca** almacene dato de negocio de tenant
  (invariante a preservar en cambios futuros; ver `raw_json = {}` arriba). Los clientes reales (AEAT
  SOAP mutual-TLS con el certificado de Julio, VIES, BORME) se ejercen **solo en staging**; en CI van
  doblados tras la interfaz `CifResolver`. Pendiente de Julio: certificado electrónico para AEAT censal
  y decidir si se contrata una API comercial de pago.
- **Integridad de un recurso mutable compartido**: `cif_lookups` es el **único** recurso mutable que
  todos los tenants comparten a través del rol runtime; un valor corrupto (p. ej. un `official_name`
  equivocado) afectaría a **todos** los tenants en un cache-hit, no solo a uno. Se acepta porque: (a)
  solo contiene **datos públicos** (no hay fuga de negocio entre asesorías), (b) está **keyed por
  `(cif, source)`**, así que una entrada mala afecta solo a ese CIF+fuente, (c) **caduca por TTL** y se
  re-fetcha (una corrupción es transitoria, no permanente), y (d) **envenenarla requiere** o bien
  inyectar un resolver malicioso (solo posible en test, donde se inyectan dobles) o comprometer la
  fuente/red real (fuera del modelo de amenaza de esta capa). No hay escritura de la caché por input
  directo del tenant: solo la escribe el servicio con lo que devuelve un resolver.

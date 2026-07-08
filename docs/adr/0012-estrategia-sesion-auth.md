# ADR-0012: Estrategia de sesión y autenticación (S1.3)

- **Estado**: aceptado
- **Fecha**: 2026-07-08
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: PLAN MAESTRO §3 (identidad), spec `docs/specs/S1.3-auth-jwt-totp.md`,
  ADR-0001 (RLS de dos niveles), ADR-0004 (subdominios). Issues #50 (rol runtime), #52 (infra Redis).

## Contexto
S1.1 aísla los datos por tenant con RLS y S1.2 resuelve el subdominio a su tenant, pero hasta ahora la
app no sabe **quién** hace cada petición ni si tiene permiso. S1.3 pone la puerta de entrada: login con
email + contraseña en el subdominio de la asesoría, opcional u obligatoriamente con segundo factor
(TOTP), y una sesión con la que operar sin reteclear la contraseña, de modo que cada petición de negocio
corra dentro de `tenant_session` (RLS de S1.1 efectiva).

Restricciones de dominio: multi-tenant (mismo email puede existir en dos asesorías y son cuentas
distintas), anti-enumeración (no revelar si una cuenta existe), la regla dura "el token identifica pero
el subdominio aísla", y los `platform_admin` (Julio, Alberto) que entran por `panel` sin pertenecer a
ninguna asesoría con TOTP obligatorio.

## Decisión
Autenticación **a medida** sobre piezas estándar, no un framework monolítico:

- **Contraseñas: Argon2id** (`argon2-cffi`). Solo se persiste el hash (`users.password_hash`); nunca la
  contraseña en claro, ni en logs. La verificación se ejecuta también cuando el usuario no existe (hash
  señuelo) para no filtrar por latencia (anti-enumeración). Política: mínimo 12 caracteres, máximo 128
  (acota el coste de hashing frente a DoS).
- **Access token: JWT HS256 de vida corta** (~15 min, `pyjwt`), con `sub`, `tenant_id`, `role`, `exp`.
  Viaja en la cabecera `Authorization: Bearer` (el frontend lo guarda en memoria).
- **Refresh rotativo con detección de reuso**, en **cookie httpOnly, Secure, SameSite=Strict** acotada a
  las rutas de auth. Cada uso rota el token e invalida el anterior; presentar un refresh ya rotado (señal
  de robo) **revoca la familia entera**. El estado (familia, token vigente, revocación) vive en Redis con
  TTL = vida del refresh.
- **Segundo factor TOTP** (`pyotp`, RFC 6238, tolerancia ±1 ventana): **obligatorio** para
  `platform_admin`, **opcional** para `tenant_admin`, no ofrecido a `user` en S1.3.
- **El token identifica, el subdominio aísla**: una dependencia por petición valida el JWT, exige que su
  `tenant_id` case con el tenant del subdominio (403 si no casa en un host de tenant; 401 sin token o si
  el subdominio no resuelve) y abre `tenant_session`. Ninguna ruta de negocio corre sin ese contexto.
- **Rate-limit en Redis**: por (IP + email) —5 fallos/15 min bloquean el 6º intento con 429, sin revelar
  si la contraseña era correcta; un login correcto resetea el contador— y un tope más grueso por IP (20)
  como defensa en profundidad frente al barrido de emails (credential spraying).
- **Fallo cerrado**: si Redis no responde, login/refresh/activación devuelven 503 (nunca "pasa todo el
  mundo"): sin Redis no se puede comprobar el límite ni registrar la rotación del refresh.
- **Primer acceso (activación)**: **cuenta activable = `status = 'active'` + `password_hash IS NULL`**. Un
  token de activación de un solo uso (TTL 72 h, en Redis) fija la contraseña (Argon2id) y genera el secreto
  TOTP, devolviendo la URI `otpauth://` para el QR. El secreto solo se **enrola** en la cuenta al
  **confirmar** el TOTP; así un `platform_admin` no puede entrar hasta confirmar y un `tenant_admin` que
  omita la confirmación se queda con login solo-contraseña. Para `platform_admin`, el token lo genera un
  script de siembra que crea la cuenta ya con `status = 'active'` (la entrega por email es S1.4).
  - **Frontera activación / aprobación**: la activación **no** toca `status`. La transición
    `pending -> active` (aprobación de un alta) es gate de **S1.4**, no de S1.3. Consumir un token de
    activación sobre una cuenta que no es activable (pendiente de aprobación, o ya con contraseña) es un
    no-op: el guard atómico `WHERE status = 'active' AND password_hash IS NULL` de
    `activation_set_password` devuelve 0 filas y la API responde 401. El enrolado del TOTP tiene el guard
    simétrico `WHERE totp_secret IS NULL`.

### Desviación consciente del listado tentativo del plan
El §1 del plan mencionaba FastAPI-Users / slowapi. Se implementa a medida porque el modelo `users` ya
está definido y es multi-tenant, y la atadura token↔subdominio, la rotación con detección de reuso y el
rate-limit por (IP+email) son requisitos que esas librerías no cubren de forma natural.

## Enmienda a ADR-0001: `platform_admin` sin asesoría
ADR-0001 asumía que todo usuario pertenece a un tenant. Un `platform_admin` no pertenece a ninguna
asesoría, así que `users.tenant_id` pasa a ser **NULLABLE**, atado por un CHECK a que rol y pertenencia
sean coherentes: `(role = 'platform_admin') = (tenant_id IS NULL)`, más un índice único parcial de email
donde `tenant_id IS NULL` (email único entre platform_admin, que `UNIQUE(tenant_id, email)` no garantiza
por ser los NULL distintos).

Su aislamiento sigue garantizado por la RLS: ningún contexto de tenant casa una fila con `tenant_id`
nulo, así que el rol runtime **nunca** ve a un `platform_admin` por lectura directa. El único camino para
autenticarlo es `find_platform_admin(email)`, función `SECURITY DEFINER` acotada (mismo patrón que
`resolve_tenant` de S1.2: dueño `autoken_definer` con BYPASSRLS, `search_path` blindado, `REVOKE ALL FROM
PUBLIC` + `GRANT EXECUTE` al rol runtime, devuelve solo `platform_admin`). La activación de usuarios sin
tenant usa el mismo patrón (`activation_set_password`, `activation_enroll_totp`), gobernada por el token
de un solo uso. El rol runtime sigue **NOBYPASSRLS**; la RLS de S1.1 queda intacta.

## Notas de robustez (ronda de hardening tras auditoría)
Refinamientos aplicados sin cambiar el comportamiento observable de la spec:

- **Rate-limit a prueba de proxy inverso**: la IP del rate-limit (C17/C22) se deriva de
  `X-Forwarded-For` **solo** si la petición viene de un proxy de confianza (`trusted_proxies` en Settings;
  vacío por defecto = nunca se confía en XFF crudo). Sin esto, tras Traefik/Caddy `request.client.host`
  sería la IP del proxy —la misma para todos— y 20 fallos de cualquiera bloquearían el login de toda la
  plataforma. En producción se fija `trusted_proxies` a la red del proxy y uvicorn arranca con
  `--proxy-headers --forwarded-allow-ips=<misma lista>`.
  - **Foot-gun `TRUSTED_PROXIES="*"`** (opt-in, no default): confía en el `X-Forwarded-For` más a la
    izquierda venga de donde venga y por tanto **desactiva la protección anti-spoofing** del rate-limit
    por IP (un atacante rota la cabecera en cada intento y no llega al tope). Solo es aceptable si un
    proxy de confianza **reescribe siempre** `X-Forwarded-For`; en cualquier otro caso se usa la lista
    de IPs concretas del proxy (primer salto no confiable desde la derecha).
- **Rotación de refresh atómica**: la comprobación (revocación / reuso / subdominio) y el fijado del nuevo
  token vigente se ejecutan en un único script Lua, sin ventana TOCTOU. La detección de reuso (revocar la
  familia) se mantiene.
- **`/auth/refresh` re-valida el subdominio** (defensa en profundidad): el `tenant_id` de la familia del
  refresh debe casar con el tenant del subdominio por el que llega; si no, no se rota (no se revoca la
  familia legítima) y se responde 401. Coherente con "el subdominio aísla".
- **Fallo cerrado (503) centralizado**: el mapeo `RedisError -> 503` vive en una sola pieza HTTP
  (`_redis_guard`), no repetido por endpoint.

## Alternativas consideradas
- **Sesión en cookie de servidor (stateful) para el access**: obliga a mirar el store en cada petición y
  complica el escalado horizontal; el JWT corto + refresh en Redis da revocación efectiva (por familia y
  vía suspensión del tenant) sin ese coste por petición.
- **Access de vida larga sin refresh**: no se puede revocar antes de `exp`; se descarta.
- **Refresh sin rotación**: un refresh robado vale hasta caducar sin señal de robo; la rotación con
  detección de reuso lo detecta al siguiente uso legítimo.
- **`platform_admin` como tenant "plataforma" ficticio**: mete una fila especial en el aislamiento y
  complica las políticas; el `tenant_id` nulo + `SECURITY DEFINER` acotado es más limpio.
- **FastAPI-Users / slowapi**: ver "desviación consciente" arriba.

## Consecuencias
- (+) Sesiones robustas: hash fuerte, 2FA, refresh con anti-robo, rate-limit y fallo cerrado.
- (+) La identidad la manda el token pero el aislamiento lo manda el subdominio: un token robado de una
  asesoría no sirve en otra (403), y suspender el tenant invalida las sesiones vivas al instante (el
  subdominio deja de resolver).
- (+) `platform_admin` sin asesoría sin agujerear la RLS: invisible salvo por el camino acotado.
- (−) Nueva dependencia de infraestructura: **Redis** es crítico en el camino de login/refresh/activación
  (fallo cerrado). Debe estar disponible en dev, CI y producción.
- (−) Disciplina: toda ruta de negocio debe pasar por la dependencia de identidad (nunca abrir sesión de
  BD sin contexto de tenant validado contra el subdominio).
- (−) Diferido (fuera de alcance de S1.3, ver spec §6): entrega por email del token de activación (S1.4),
  RBAC por endpoint y acceso cross-tenant del `platform_admin` (S1.6), scoping por `company_id` en sesión
  (S1.6), rechazo de replay de TOTP y cabeceras de seguridad globales (hardening S5).

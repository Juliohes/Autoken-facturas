# 📜 Auditoría de código — Autoken Facturas v2

> **Fecha:** 2026-06-22
> **Alcance:** código existente HOY (Fase 0, esqueleto + módulo OCR). Solo lectura.
> **Método:** 3 agentes independientes (buenas prácticas/SOLID, seguridad, tests) + recon previo.
> **Estado del repo:** rama `develop`, ~670 líneas backend / ~160 frontend.

**Veredicto global:** proyecto muy bien gobernado. **Nada está ardiendo.** Cero hallazgos
críticos explotables hoy. El trabajo real se concentra en un solo módulo: `ocr/verification.py`.

Cada hallazgo lleva:
- 🏷️ **Campo** — el área de software a la que pertenece.
- 📚 **Estudiar** — qué aprender para dominarlo.

---

## 🧙 1. Buenas prácticas / SOLID

### 🟠 BP-1 — `check_tax_line` es código muerto; el cuadre de totales es laxo
`verification.py:164-201`. `check_invoice_totals` recibe las cuotas ya calculadas y **no
comprueba** que cada cuota cuadre con su base × IVA%. Las firmas no encajan
(`(base, iva_pct, cuota)` vs `list[(base, cuota)]`) → nadie llama a `check_tax_line`. Es el
agujero que el OCR puede colar (anti-alucinación incompleta).
- 🏷️ **Campo:** Diseño de software / composición de funciones · código muerto (dead code).
- 📚 **Estudiar:** *Refactoring* (Martin Fowler) cap. "Dead Code" y "Composing Methods";
  cohesión funcional; cómo detectar dead code con cobertura.

### 🟠 BP-2 — Clasificación de tipos de CIF demasiado laxa
`verification.py:28-32, 104-109`. Los tipos `N/W/R` caen en la rama "dígito o letra" cuando
probablemente deben exigir **letra** (según AEAT). Falsos positivos en el CIF de contraparte.
- 🏷️ **Campo:** Lógica de dominio / corrección algorítmica.
- 📚 **Estudiar:** algoritmo oficial de control de CIF/NIF (tabla censal AEAT);
  *domain-driven design* (validación invariantes de dominio). **Verificar contra fuente, nunca de memoria.**

### 🟠 BP-3 — Service-locator en vez de inyección de dependencias
`platform_admin/health.py:27`. `get_settings()` se llama **dentro** del handler en lugar de
`Depends(get_settings)`. Rompe DIP y deja los tests sin `app.dependency_overrides`. Fix coste cero.
- 🏷️ **Campo:** SOLID (Dependency Inversion) · inyección de dependencias.
- 📚 **Estudiar:** el principio DIP; sistema de `Depends` de FastAPI; patrón Service Locator
  vs Dependency Injection (por qué DI gana en testabilidad).

### 🟡 BP-4 — Validadores no defienden contra `None`
Si el OCR entrega `None` (regla anti-alucinación = `null`), `_normalize(None)` lanza
`AttributeError` en vez de devolver `CheckResult(False, ...)`.
- 🏷️ **Campo:** Robustez / programación defensiva · contratos de tipos.
- 📚 **Estudiar:** *defensive programming*; "fail fast vs fail safe"; tipos opcionales y
  validación de fronteras (boundary validation).

### 🟡 BP-5 — `log_level: str` traga valores inválidos en silencio
`logging.py:17` cae a `INFO` si el nivel no existe, sin avisar. Fallo de config silencioso.
- 🏷️ **Campo:** Configuración / *fail-loud design*.
- 📚 **Estudiar:** validación de configuración con Pydantic (`Literal`/enums); "configuration
  as code"; por qué los fallos silenciosos son deuda oculta.

### 🔵 BP-6 — `CheckResult` no preparado para los niveles L2/L3/L4 del CIF
`verification.py:41-50`. `bool + str` aguanta L1, pero L2 (supplier master), L3 (AEAT/VIES) y
L4 (caché) necesitan más (fuente, nivel, bloqueante vs aviso).
- 🏷️ **Campo:** SOLID (Open/Closed) · extensibilidad de diseño.
- 📚 **Estudiar:** principio OCP; diseño de tipos de resultado (Result/Either pattern);
  evolución de contratos sin romper clientes.

### ✅ Lo bueno
`Decimal` en todo el dinero (no `float`), módulo puro sin I/O, application-factory + lifespan
idiomáticos, mypy strict + ruff completo. Algoritmos NIF/NIE mod-23 e IBAN mod-97 correctos.

---

## 🧪 2. Tests

### 🔴 TST-1 — Ramas del CIF letra-vs-dígito sin probar
`KPQS` (control = letra) y `ABEH` (control = dígito): ninguna rama de "mismatch" se ejercita.
La lógica de negocio más delicada sin red.
- 🏷️ **Campo:** Cobertura de ramas (branch coverage) · testing de lógica de dominio.
- 📚 **Estudiar:** *branch vs line coverage*; tablas de decisión; testing basado en
  particiones de equivalencia.

### 🔴 TST-2 — Rama "no reconocido" del dispatcher sin probar
`validate_tax_id` línea 127: un identificador que no es NIF/NIE/CIF (basura típica del OCR)
nunca se prueba.
- 🏷️ **Campo:** Testing de caminos de error / edge cases.
- 📚 **Estudiar:** *negative testing*; análisis de valores límite (boundary value analysis).

### 🟠 TST-3 — Fronteras de tolerancia sin probar
`check_tax_line`/`check_invoice_totals`: nadie prueba diff == 0,02 → válido / 0,03 → inválido.
Un cambio de `>` a `>=` pasa el CI en verde.
- 🏷️ **Campo:** Análisis de valores límite (boundary value analysis).
- 📚 **Estudiar:** boundary testing; *mutation testing* (cazaría justo este cambio de operador).

### 🟠 TST-4 — Los tests de fallo no asertan el `.reason`
Asertan solo `.valid` y tiran el mensaje en español (el que ve el usuario en la pantalla de
revisión). Sin red de regresión sobre los mensajes anti-alucinación.
- 🏷️ **Campo:** Calidad de aserciones / testing de comportamiento observable.
- 📚 **Estudiar:** "test behavior, not implementation"; aserciones significativas; por qué un
  mensaje de error es parte del contrato.

### 🟠 TST-5 — `CorrelationIdMiddleware` sin test unitario
El binding del id al contexto de logs (lo que aparece en producción) no se verifica.
- 🏷️ **Campo:** Testing de middleware / observabilidad.
- 📚 **Estudiar:** testing de middleware ASGI/Starlette; testing de logging estructurado.

### 🟡 TST-6 — Sin cobertura de ramas en CI
No hay `pytest-cov --cov-branch --cov-fail-under`. Es la herramienta que cazaría TST-1..3 sola.
- 🏷️ **Campo:** Automatización de calidad / CI quality gates.
- 📚 **Estudiar:** `pytest-cov`; umbrales de cobertura como gate; cobertura de ramas vs líneas.

### 🟥 TST-7 — El gate de aislamiento es `assert True` (seguridad falsa)
`test_tenant_isolation.py` pasa trivialmente, pero es un gate **bloqueante** de CI. Defendible
HOY (no hay superficie multi-tenant), pero el riesgo es de **proceso**: nada te obliga a
rellenarlo en S1.7.
- 🏷️ **Campo:** Estrategia de testing / CI gates · riesgo de proceso.
- 📚 **Estudiar:** *test doubles* vs placeholders; cómo diseñar gates que no mientan;
  `xfail`/`skip` con razón; testing de aislamiento multi-tenant (RLS).

**Cobertura real:** ~85% líneas pero solo **~60-70% ramas** en `verification.py`. Tenancy: 0%.

---

## 🛡️ 3. Seguridad

### 🟠 SEC-1 — Contraseña por defecto `autoken` versionada
`config.py:38` y `docker-compose.yml:17,32`. Trampa para el día del despliegue si falta `.env`.
- 🏷️ **Campo:** Gestión de secretos / *secure defaults* (OWASP A05/A07).
- 📚 **Estudiar:** OWASP Top 10 (A05 Misconfiguration, A07 Auth Failures); "secure by default";
  gestión de secretos (Doppler/SOPS/Vault).

### 🟡 SEC-2 — `X-Correlation-ID` entrante se confía y se refleja sin sanear
`middleware.py:25,31`. Validar `^[A-Za-z0-9._-]{1,128}$` en el borde.
- 🏷️ **Campo:** Validación de entrada / inyección (OWASP A03) · log injection.
- 📚 **Estudiar:** *input validation* en bordes de confianza; HTTP response splitting / CRLF
  injection; log injection y por qué un renderer JSON la contiene.

### 🟡 SEC-3 — `/docs` y `/health` abiertos siempre
`main.py:33-34`, `health.py`. En prod exponen el contrato de la API y filtran
`version`/`environment`.
- 🏷️ **Campo:** Exposición de información / control de acceso (OWASP A01/A05).
- 📚 **Estudiar:** *information disclosure*; superficie de ataque; healthchecks
  (liveness/readiness) y qué información es seguro exponer.

### 🟡 SEC-4 — Auditorías de dependencias no bloquean + sin lockfile en backend
`ci.yml:121-133` (`continue-on-error` + `|| true`); `pyproject.toml` solo lower-bounds, sin
lockfile → builds no reproducibles.
- 🏷️ **Campo:** Supply-chain security / reproducibilidad de builds (OWASP A06).
- 📚 **Estudiar:** *software supply chain* (SLSA); lockfiles y `--require-hashes`; `uv`/pip-tools;
  dependency confusion / typosquatting.

### 🔵 SEC-5 — gitleaks en CI se baja por `curl` sin checksum
`ci.yml:113-117`. El binario que valida tus secretos no se verifica. Actions pineadas por tag
flotante (`@v4`).
- 🏷️ **Campo:** Integridad de software / supply-chain del CI (OWASP A08).
- 📚 **Estudiar:** verificación de integridad (SHA-256/firmas); pineado de GitHub Actions por SHA;
  ataques a pipelines de CI.

### 🔵 SEC-6 — Redis sin auth · sin security headers · sin rate limiting
`docker-compose.yml` (Redis), `main.py` (headers). No explotable hoy; decidir reparto Caddy vs app.
- 🏷️ **Campo:** Hardening de infraestructura / defensa en profundidad.
- 📚 **Estudiar:** security headers (CSP, HSTS, X-Frame-Options); rate limiting; *defense in depth*;
  hardening de Redis.

### ✅ Lo bueno
Higiene de secretos excelente (gitleaks pre-commit + CI, `.gitignore` exhaustivo, deny-rule en
`.env*`). Dockerfile no-root. Los 3 vectores sospechados (DoS por IBAN, ReDoS, input ilimitado)
**descartados con verificación**: `len > 34` corta antes del `int()`.

---

## ⚔️ Dónde coincidieron los scouts (máxima confianza)

1. **`ocr/verification.py` (CIF)** — SOLID + Tests, mismo módulo, dos ángulos. **Jefe final nº1.**
2. **`middleware.py`** — lo tocaron los 3 (acoplamiento, header sin sanear, sin test).
3. **Gate `assert True` de aislamiento** — riesgo de proceso, no de código.

---

## 🗺️ Otras auditorías candidatas (por valor hoy)

**Las que más valen AHORA (antes de construir encima):**
- 🏛️ **Arquitectura / preparación para el plan** — ¿la estructura aguanta RLS de 2 niveles,
  workers, multi-tenant? (Recomendada nº1 por tu objetivo L3: defender arquitectura.)
  📚 *Software Architecture: The Hard Parts*; *Fundamentals of Software Architecture* (Richards/Ford).
- 🧩 **Patrones de diseño** — Strategy (motores OCR), Chain of Responsibility (L1-L4 del CIF),
  Repository (acceso a datos con RLS).
  📚 *Design Patterns* (GoF); refactoring.guru.
- 📐 **Modelo de datos / diseño de BD** — antes de la primera migración: índices que empiezan por
  `tenant_id`, RLS FORCE, tabla de contrapartes/caché CIF.
  📚 PostgreSQL Row-Level Security; diseño multi-tenant; *Designing Data-Intensive Applications*.

**Clásicas, valiosas pero algo prematuras hoy:**
- ⚡ Rendimiento / escalabilidad · ♿ Accesibilidad + UX (agentes dedicados) ·
  🔭 Observabilidad · 📜 Documentación/ADRs · 💰 Coste por factura.
- 🤖 **Específica de IA/OCR** (clave en Fase 1): anti-alucinación, prompt-injection en facturas,
  residencia de datos RGPD.

---

## 🎯 Recomendación de ataque
Cerrar `verification.py` con **Bug-First TDD**: escribir primero los tests que fallan
(ramas del CIF + fronteras de tolerancia), luego el fix. Es el módulo donde coincidieron 2 de 3
scouts y es el valor actual del producto.

---
---

# 🏛️ SEGUNDA RONDA — Auditorías de DISEÑO (arquitectura, patrones, modelo de datos)

> **Fecha:** 2026-06-22 (misma sesión).
> **Diferencia clave:** en Fase 0 apenas hay código. Estas tres auditorías auditan el **DISEÑO
> PLANIFICADO** (PLAN MAESTRO §3-4 + ADRs), no código. Es el momento más barato para cazar fallos:
> arreglar el plano cuesta una conversación; arreglar el cimiento vertido cuesta un sprint.
> **Convención:** DESIGN-RISK = arréglalo en el plan AHORA · BUILD-RISK = vigílalo al implementar.

---

## 🏛️ 4. Arquitectura

**Veredicto:** plan de gobernanza excepcional sobre arquitectura sólida y convencional-en-el-buen-sentido.
El riesgo no está en las decisiones tomadas, sino en las que el plan deja **en prosa** en los tres puntos
donde el diseño se gana o se pierde.

### 🔴 ARQ-1 — RLS + pooling de asyncpg: fuga de contexto de tenant entre peticiones (el dragón nº1)
PLAN §3.3, ADR-0001. El RLS descansa en `SET app.tenant_id` (variable de sesión). Con pool de conexiones,
una conexión que vuelve al pool **sin resetear** queda contaminada → la siguiente petición de otro tenant
opera con el contexto del anterior. Cruce silencioso (rompe Regla de Oro #5). **El gate §8 lo dejaría pasar
porque sus tests son secuenciales, no concurrentes.** Invisible bajo carga baja, explota en producción.
- **Fix:** decidir en ADR-0001 entre `SET LOCAL` dentro de transacción por petición (lo más robusto) o
  reset explícito en el checkin del pool. Añadir **test de aislamiento concurrente** (`asyncio.gather`).
- 🏷️ **Campo:** Data engineering / connection management · concurrencia.
- 📚 **Estudiar:** "RLS connection pooling tenant leak"; `SET LOCAL` vs `SET`; eventos de pool de SQLAlchemy (`checkin`/`reset_on_return`).

### 🔴 ARQ-2 — Idempotencia del job OCR ausente del diseño
PLAN §4 capa 2-3, S2.3. arq reintenta jobs (timeout, crash, redeploy). Sin idempotencia → doble llamada a
Azure/Gemini (**coste duplicado en `ocr_extractions.cost`, que es la base del pricing**) + filas duplicadas.
- **Fix:** clave de idempotencia = `file_hash_sha256` + engine; comprobar antes de llamar al motor; `job_id` determinista derivado del hash.
- 🏷️ **Campo:** Distributed systems / colas.
- 📚 **Estudiar:** idempotency keys; at-least-once delivery; dedup por hash de contenido.

### 🔴 ARQ-3 — Camino cross-tenant del `platform_admin` rompe el propio modelo RLS
PLAN §3.3. El admin de plataforma es el único actor legítimamente cross-tenant. Si accede vía `BYPASSRLS`,
abre una puerta que esquiva toda la defensa; si itera por tenants en la app, vuelve al "filtro en el ORM"
que el ADR rechazó. El plan no lo decide.
- **Fix:** vistas agregadas de métricas (sin PII) para el 95%; acceso a datos concretos vía endpoint con
  `SET app.tenant_id` explícito + entrada en `audit_log` **antes** de la query. Evitar `BYPASSRLS` en la app web.
- 🏷️ **Campo:** Security architecture / least privilege.
- 📚 **Estudiar:** `BYPASSRLS`; patrón "break-glass access with mandatory audit"; separación de planos lectura/datos.

### 🟠 Segundo anillo
- **ARQ-4 — Doble política RLS "según rol" sin especificar:** "ausente" no debe significar "ve todo"
  (fail-closed, no fail-open). Riesgo de escalada *dentro* del tenant por bug.
  🏷️ Authorization design / RBAC en capa de datos · 📚 RLS con `current_setting(..., true)`, fail-closed.
- **ARQ-5 — Frontera async del upload difusa:** ClamAV aparece en §3.5 (upload) Y §4 (worker). Fijar:
  request síncrono = MIME+tamaño+encolar; worker = ClamAV+OCR. Es el cuello de escalado de S5.5.
  🏷️ Async architecture / backpressure · 📚 sync/async boundaries, por qué el AV nunca va en el hilo del request.
- **ARQ-6 — L3 (AEAT/VIES) frágil:** §11.8.3 ya dice lo correcto (timeout → "revisar manual", nunca bloquea
  por caída de tercero), pero no fija *dónde* corre L3. Recomienda: en el worker, asíncrono respecto a la
  pantalla; el bloqueo del botón se basa en L1+L2 locales, no en L3.
  🏷️ Integration architecture / resilience · 📚 circuit breaker, cache-aside con TTL, anti-corruption layer.
- **ARQ-7 — El "árbitro por campo" es prosa, no contrato:** con 6+ motores candidatos, definirlo como
  función pura testeable (como `verification.py`) → añadir motor = añadir adaptador, cero cambios en el árbitro.
  🏷️ Domain modeling / strategy · 📚 Strategy + ensemble/voting, funciones puras como núcleo testeable.
- **ARQ-8 — Frontera `ocr` ↔ `invoice_intake` sin contratar:** riesgo de acoplamiento bidireccional (el peor).
  Fix: `ocr` no conoce `invoice_intake`; emite evento `OcrCompleted` por `shared/events`; una sola dirección.
  🏷️ DDD / bounded contexts · 📚 acyclic dependency principle, domain events para desacoplar.
- **ARQ-9 — Único dominio de fallo** (un Postgres, un MinIO, un VPS): backup ≠ disponibilidad. Declarar
  RTO/RPO **conscientemente** en ADR-0005, no accidentalmente.
  🏷️ SRE / availability & DR · 📚 RTO/RPO, single point of failure, backup vs HA.

### 🟡 Afinado / honestidad de ADRs
ARQ-10 (semántica del bus `shared/events`: in-process vs Redis), ARQ-11 (CQRS-light no sobre-ingenierizar),
ARQ-12 (portabilidad AWS "sin reescritura" optimista — Caddy on-demand TLS no tiene equivalente en ALB),
ARQ-13 (cifrado por tenant decidido en S5 pero afecta al esquema de S1: decidir alcance ahora).

### ✅ Lo bueno
RLS `FORCE` + usuario sin owner/superuser, índice compuesto que empieza por `tenant_id`, aislamiento por host
(no path), gate de aislamiento ejecutable en CI, `verification.py` puro sin red, "identidad propia se conoce,
no se lee", `cif_lookups` como caché global razonada.

### 🏆 Top-5 arquitectura (cerrar antes de Sprint 1/2)
1. 🔴 ARQ-1 RLS+pooling (`SET LOCAL`-en-transacción + test concurrente). Bloquea S1.1.
2. 🔴 ARQ-2 Idempotencia del job OCR (`file_hash + engine`). Bloquea S2.3.
3. 🔴 ARQ-3 Camino cross-tenant del platform_admin sin `BYPASSRLS`. ADR antes de Sprint 4.
4. 🟠 ARQ-5 Frontera async del upload. Bloquea S2.1.
5. 🟠 ARQ-8 Dirección de dependencia `ocr` → evento → `invoice_intake`. ADR antes de Sprint 2.

---

## 🧩 5. Patrones de diseño

**Veredicto:** el plan **ya implica** los patrones correctos (usa el vocabulario justo sin sobre-prometer
infra). El riesgo es aplicarlos demasiado pronto (pattern-worship) o perder la disciplina de núcleo puro que
`verification.py` inauguró. Regla aplicada: *pain first, name second*.

### 🟢 Comprometer en el diseño YA
- **PAT-1 — Result/Outcome enriquecido (L1-L4).** `CheckResult` ya existe; **no lo toques** (L1 puro y
  estable). Crea `VerificationOutcome{status, source, blocking, official_name, reason}` para la cadena de
  contraparte; mapea 1:1 con los campos nuevos de `invoices`. Es el contrato del que cuelga la pantalla de
  revisión; sin él, todo gotea. Decídelo en ADR-0011.
  🏷️ `ocr/counterparty/outcome.py` · 📚 Scott Wlaschin *Domain Modeling Made Functional* (Result type); "boolean blindness".
- **PAT-2 — Strategy + Factory de motores OCR.** Frontera = el **2º motor** (Fase 1). Define `OcrEngine`
  Protocol + `ExtractionResult` de mínimo-común-denominador antes de implementar Mistral/GPT, o el árbitro se
  llena de `if engine == ...`.
  🏷️ `ocr/engines/` · 📚 GoF Strategy + Factory Method; Brandon Rhodes "Strategy Pattern in Python" (Protocol vs ABC).
- **PAT-3 — Ports & Adapters / functional core.** Ya iniciado en `verification.py` (puro, sin red).
  Declárelo explícito en el ADR para que árbitro y validación **nunca** toquen red. Es lo que hace la regla
  anti-alucinación verificable con tests unitarios.
  🏷️ `ocr/` (core vs borde) · 📚 Cockburn (Ports & Adapters); Gary Bernhardt "Boundaries" (functional core, imperative shell).

### 🟡 Diseñar ahora, implementar cuando duela
- **PAT-4 — Chain of Responsibility (CIF L1→L2→L3→L4).** Cadena con early-exit y orden de coste (L4 caché
  cortocircuita antes de L3; L1 inválido corta todo). Diséñala en ADR-0011, impleméntala en S2.8 cuando exista
  L2. Los feature-flags por tenant la harían explotar como God function si fuera `if` anidados.
  🏷️ `ocr/counterparty/chain.py` · 📚 GoF Chain of Responsibility (¡no confundir con Pipeline!).
- **PAT-5 — Adapter (fuentes externas).** `CifResolver` (puerto) + adapters (`AeatCensalAdapter`,
  `ViesAdapter`...). Timeout/caché/circuit-breaker en un **decorador del puerto**, no en cada adapter.
  🏷️ `ocr/counterparty/resolvers/` · 📚 GoF Adapter; Nygard *Release It!* (Stability Patterns).
- **PAT-6 — Repository + tenant-context dependency.** Sprint 1, el punto único donde se setea `app.tenant_id`.
  Repos **concretos por agregado**, NO un `Repository[T]` genérico (over-engineering). RLS hace el filtrado;
  el repo centraliza el seteo de la variable de sesión.
  🏷️ `<module>/repository.py` + `shared/db.py` · 📚 Fowler *PoEAA* (Repository + Unit of Work); Vernon *IDDD* cap.12.
- **PAT-7 — Pipeline funcional (NO Template Method)** para el flujo OCR de 4 capas; el árbitro como función
  pura `arbitrate(...)`. En Python la herencia con hooks casi nunca compensa.
  🏷️ `ocr/pipeline.py` + `ocr/arbiter.py` · 📚 Pipes-and-Filters (POSA vol.1); Fowler *Collection Pipeline*.
- **PAT-8 — Domain Events in-process** (S2, síncrono, NO Redis pub/sub): `ocr_corrections` + `audit_log` +
  supplier master reaccionan a un evento emitido una vez. Outbox solo si Verifactu lo pide.
  🏷️ `shared/events.py` · 📚 Vernon *IDDD* cap.8; *Cosmic Python* cap.8-9 (message bus in-process).
- **PAT-9 — CQRS-light** (S3): read models planos en `reporting/`, queries de solo-lectura → DTOs Pydantic.
  Nada de event-sourcing ni bases separadas.
  🏷️ `reporting/queries.py` · 📚 Fowler *CQRS* (para saber dónde parar); *Cosmic Python* cap.12.

### ⚠️ Anti-patrones bajo vigilancia
| Anti-pattern | Dónde acecha | Severidad |
|---|---|---|
| **Service Locator** | `health.py` (`get_settings()` interno en vez de `Depends`) | 🟢 corregir ya, 1 línea |
| **God Object** | el `process_invoice()` del worker OCR (motores+árbitro+validación+master+audit+dataset) | 🟢 **el mayor riesgo del proyecto** |
| **Leaky abstraction** | bounding boxes de Azure / SOAP de VIES asomando en el contrato | 🟢 decidir antes del 2º motor |
| **Anemic Domain Model** | lógica de bloqueo en "services" en vez del agregado `Invoice` | 🟡 evitar en S2 |

### 🏆 Top-5 patrones a comprometer
1. 🟢 PAT-1 Result/Outcome enriquecido (el contrato base). ADR-0011.
2. 🟢 PAT-2 Strategy + Factory de motores (frontera = 2º motor).
3. 🟢 PAT-3 Ports & Adapters / functional core (declararlo y protegerlo).
4. 🟡 PAT-4 + PAT-5 Chain + Adapter del CIF (diseñar ahora, S2.8 implementar).
5. 🟡 PAT-6 Repository + tenant-context dependency (Sprint 1).

---

## 📐 6. Modelo de datos / Diseño de BD

**Veredicto:** modelo conceptual **sano**; lo que falta es convertir las reglas de prosa en **constraints de
motor**. RLS defiende en lectura; las FK compuestas, los UNIQUE y los CHECK son la armadura que el plan
describe en español pero aún no ha forjado en DDL. (Momento: `migrations/versions/` vacío — el más barato.)

### 🔴 Cerrar ANTES de la primera migración (S1.1)
- **BD-1 — FK no garantizan confinamiento de tenant.** Una FK simple `invoice_tax_lines.invoice_id →
  invoices.id` no impide que un tramo del tenant A apunte a una factura del tenant B. RLS filtra lecturas; la
  integridad referencial cruzada no la cubre. **Fix:** FK **compuestas** con `tenant_id` (requiere
  `UNIQUE(id, tenant_id)` en el padre). RLS protege SELECT; las FK compuestas protegen INSERT/UPDATE.
  🏷️ Integridad referencial / aislamiento a nivel de esquema · 📚 "Composite foreign keys for tenant isolation".
- **BD-2 — `cif_lookups` global filtra inteligencia de negocio (side channel).** El contenido (CIF→razón
  social) es público, pero la tabla revela **qué CIFs ha consultado la plataforma**: un cache-hit instantáneo
  permite inferir que otro tenant trabaja con ese proveedor. En un SaaS de asesorías, la cartera de
  proveedores es info competitiva. Defendible solo si se documenta la amenaza en un ADR y se mitiga (nunca
  exponer la tabla ni `fetched_at` al tenant).
  🏷️ Caché multi-tenant / canales laterales / privacidad de metadatos · 📚 "Cache side-channel in multi-tenant SaaS".
- **BD-3 — Alcance de unicidad de `file_hash_sha256` sin definir.** ¿Único por tenant, company o global? Si
  global, dos tenants con la misma factura de Endesa colisionan. Sin constraint, la detección es best-effort
  con race condition. **Fix:** `UNIQUE (tenant_id, file_hash_sha256)`.
  🏷️ Constraints de unicidad / idempotencia / race conditions · 📚 "insert and catch unique violation".

### 🟠 Mayores
- **BD-4 — Estrategia de PK no decidida.** bigint = índices compactos pero IDs enumerables → **IDOR** (S5.4).
  UUIDv4 = no enumerable pero fragmenta el B-tree. **UUIDv7** = lo mejor de ambos. Cambiar el tipo
  post-migración es cirugía con FKs colgando.
  🏷️ Estrategia de PK / IDOR / localidad de índices · 📚 "UUIDv7 vs bigint vs UUIDv4 primary key Postgres".
- **BD-5 — Denormalización contraparte vs `counterparties`.** `supplier_*`/`receiver_*` deben quedarse como
  **snapshot OCR inmutable** ✅, pero `counterparty_official_name` deriva del master → riesgo de deriva.
  **Fix:** snapshot + FK opcional `counterparty_id` al master vivo. Decisión de ADR.
  🏷️ Normalización vs snapshot histórico / 3NF · 📚 "Snapshot vs reference data in transactional records".
- **BD-6 — Faltan CHECK constraints; enums como texto libre.** Nada impide `status='aktive'` o `total`
  negativo. **Fix:** `CHECK IN (...)` (más migrable que enum nativo) + `CHECK (total >= 0)`. Hueco de spec:
  el set real de `invoices.status` no está enumerado en el plan.
  🏷️ CHECK constraints / dominio de columnas · 📚 "Postgres ENUM vs CHECK constraint trade-offs".
- **BD-7 — `audit_log` append-only sub-especificado.** "Sin permisos" es la base, pero falta: ¿hash
  **encadenado** (`hash_n = SHA256(payload_n ‖ hash_{n-1})`, detecta borrados) o por fila? + partición por
  fecha desde el día 1. Diséñalo ahora, no con 2M filas.
  🏷️ Tablas append-only / tamper-evidence / particionado · 📚 "hash chain audit log"; "declarative partitioning by range".
- **BD-8 — PKs implícitas en tablas hijas.** `invoice_tax_lines`, `memberships`, `ocr_extractions` sin PK
  declarada → duplicados silenciosos que romperían la suma de `check_invoice_totals`.
  🏷️ Claves naturales vs surrogate · 📚 "natural vs surrogate keys junction tables".

### 🟡 Menores / nits
- **BD-9** JSONB sin estrategia de índice — promover los 3 campos de oro a columnas `*_confidence` si se filtran.
  📚 "When to promote JSONB fields to columns".
- **BD-10** TTL de `cif_lookups` sin purga + TTL diferenciado para "no existe". 📚 tipo `interval` de Postgres.
- **BD-11** `timestamptz` siempre (nunca naive); faltan `created_at`/`updated_at`. 📚 "never store naive timestamps".
- **BD-12 — RLS/`REVOKE` deben vivir en las migraciones Alembic con downgrade simétrico.** Si no, una
  migración puede dejar una tabla **sin RLS** — el fallo exacto que el gate de CI debe cazar. Helper
  `apply_tenant_rls(table)`. 📚 "Alembic op.execute for RLS policies"; "reversible migrations for grants/policies".
- **BD-13 nits:** `tenants.slug` UNIQUE + `CHECK` formato; `tenant_branding` PK = `tenant_id` (1:1);
  `companies.cif` UNIQUE por tenant; `users.email` UNIQUE por tenant; `times_seen` con `UPDATE ... +1` (no read-modify-write).

### ✅ Lo bien diseñado
Regla `tenant_id`-prefijo en índices, RLS `FORCE` + usuario no-owner, `audit_log` con `payload_hash`, dinero
en `Decimal`, separación tramos/IRPF (1NF), anti-alucinación = `null`.

### 🏆 Top-5 BD (antes de la primera migración S1.1)
1. 🔴 BD-1 FK compuestas con `tenant_id` (define la forma de TODAS las FKs).
2. 🟠 BD-4 Estrategia de PK (UUIDv7 recomendado).
3. 🔴 BD-3 Unicidad de `file_hash_sha256` por tenant.
4. 🔴/🟠 BD-2 + BD-5 ADR para caché global y snapshot de contraparte.
5. 🟠 BD-7 + BD-12 `audit_log` (hash-chain + partición) y RLS en migraciones con downgrade simétrico.

---

## 🗺️ Convergencia de los tres scouts de diseño

| Punto de colisión | Arquitectura | Patrones | Modelo BD |
|---|---|---|---|
| `verification.py` puro como modelo a seguir | "buen gusto arquitectónico" | "tu mejor activo, protégelo" | "ya blindado contra float" |
| El árbitro/contrato como función pura testeable | ARQ-7 | Result object + Pipeline funcional | — |
| **Aislamiento multi-tenant con grietas no escritas** | 🔴 ARQ-1 (RLS+pooling, lectura) | PAT-6 Repository = punto único del `SET` | 🔴 BD-1 (FK compuestas, escritura) + BD-2 (caché) |
| RLS en migraciones con downgrade simétrico | — | — | 🟡 BD-12 |
| Service Locator en `health.py` | (heredado del audit de código, BP-3) | 🟢 corregir ya | — |

**El hallazgo más potente:** los tres scouts llegaron, por caminos distintos, a que **el aislamiento
multi-tenant tiene agujeros que el plan deja en prosa** — Arquitectura por el *pooling de conexiones*
(lectura), BD por las *FK compuestas* (escritura), Patrones por el *Repository como punto único del `SET`*.
Tres caras del mismo dragón, y los tres dicen lo mismo: **escríbelo en un ADR antes de Sprint 1, no después.**

---

## 🎯 Recomendación de ataque (diseño)
Antes de tocar Sprint 1, redactar **tres ADRs baratos** que cierran el 80% del riesgo de diseño:
1. **ADR-0001 ampliado** — ciclo de vida de la variable de sesión RLS (`SET LOCAL`-en-transacción) +
   FK compuestas con `tenant_id` + RLS/REVOKE en migraciones con downgrade simétrico. (ARQ-1, BD-1, BD-12)
2. **ADR nuevo (datos)** — estrategia de PK (UUIDv7), unicidad de `file_hash` por tenant, caché global
   `cif_lookups` con modelo de amenaza, snapshot vs referencia de contraparte. (BD-2/3/4/5)
3. **ADR-0011 (contraparte)** — `VerificationOutcome` enriquecido + Chain of Responsibility + Adapter del CIF,
   con timeout/caché/circuit-breaker en el borde del puerto. (PAT-1/4/5, ARQ-6)
Y dos correcciones baratas de código: el Service Locator de `health.py` → `Depends`, e idempotencia del job
OCR por `file_hash + engine` cuando nazca el worker (S2.3).

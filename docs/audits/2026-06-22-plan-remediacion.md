# Plan de remediación — Auditoría externa 2026-06-22 (Javi)

> **Qué es esto:** la *respuesta de gestión* (management response) a la auditoría externa archivada
> en [`2026-06-22-auditoria-externa-javi.md`](./2026-06-22-auditoria-externa-javi.md). Convierte cada
> hallazgo en una decisión trazable: severidad → respuesta → acción → issue → estado. El documento de
> auditoría es **inmutable** (registro); este es **vivo** (se actualiza al cerrar cada hallazgo).
> **Fuente única:** enlazado desde el PLAN MAESTRO §11.9.

## Cómo leer la tabla

- **Severidad** (de la auditoría): 🔴 crítico de diseño · 🟠 mayor · 🟡 menor · 🔵 nit/informativo · 🟥 riesgo de proceso.
- **Respuesta** (decisión de gestión):
  - **Aceptado–ADR**: requiere decisión arquitectónica formal antes de implementar.
  - **Aceptado–corregir**: fix directo con test; sin ADR.
  - **Aceptado–diferir**: válido, pero se aborda en el sprint que lo necesita.
  - **Mitigado/Ya cubierto**: total o parcialmente resuelto por trabajo en curso.
  - **EN DECISIÓN (Julio)**: contradice o matiza una decisión ya escrita → requiere tu visto bueno (ver §"Decisiones que requieren tu visto bueno").
- **Estado**: `abierto` · `en curso` · `cerrado` · `diferido` · `decisión pendiente`.

---

## Resumen ejecutivo

**Veredicto de la auditoría:** proyecto muy bien gobernado, **cero hallazgos críticos explotables hoy**.
El riesgo real no está en lo construido (≈670 líneas backend) sino en **tres puntos de diseño que el plan
deja en prosa** y que los tres scouts de diseño señalaron por caminos distintos:

1. **Aislamiento multi-tenant con grietas no escritas** — RLS+pooling (lectura, ARQ-1) · FK compuestas
   (escritura, BD-1) · Repository como punto único del `SET` (PAT-6). *Tres caras del mismo dragón.*
2. **Idempotencia del job OCR** (ARQ-2) — afecta directamente al coste, que es la base del pricing.
3. **El contrato de verificación de contraparte** (`VerificationOutcome`, PAT-1) — del que cuelga la
   pantalla de revisión y el bloqueo del botón (§11.8).

**Estrategia adoptada (coincide con la recomendación de la auditoría):** cerrar el 80 % del riesgo con
**tres ADRs baratos antes del Sprint 1** + endurecer `verification.py` con Bug-First TDD + un lote de
correcciones rápidas. Todo es **aditivo** al plan; no se elimina ninguna decisión salvo la única marcada
**EN DECISIÓN (Julio)** (ARQ-12, portabilidad AWS).

**Conteo:** 6 BP · 7 TST · 6 SEC · 13 ARQ · 9 PAT · 13 BD = **~35 hallazgos** → 8 issues accionables
(#17–#24) + decisiones de ADR + 1 decisión pendiente de Julio.

---

## 1. Código — Buenas prácticas / SOLID

| ID | Sev | Hallazgo | Respuesta | Issue | Estado |
|---|---|---|---|---|---|
| BP-1 | 🟠 | `check_tax_line` es dead code; el cuadre de totales no comprueba base×IVA% | Aceptado–corregir (Bug-First TDD) | [#20](https://github.com/Juliohes/Autoken-facturas/issues/20) | abierto |
| BP-2 | 🟠 | Clasificación de tipos de CIF N/W/R demasiado laxa | Aceptado–corregir (**verificar contra fuente AEAT**) | [#20](https://github.com/Juliohes/Autoken-facturas/issues/20) | abierto |
| BP-3 | 🟠 | Service Locator: `get_settings()` en el handler en vez de `Depends` | Aceptado–corregir (1 línea) | [#23](https://github.com/Juliohes/Autoken-facturas/issues/23) | abierto |
| BP-4 | 🟡 | Validadores no defienden contra `None` (regla anti-alucinación) | Aceptado–corregir | [#20](https://github.com/Juliohes/Autoken-facturas/issues/20) | abierto |
| BP-5 | 🟡 | `log_level` traga valores inválidos en silencio | Aceptado–corregir (`Literal`/enum) | [#23](https://github.com/Juliohes/Autoken-facturas/issues/23) | abierto |
| BP-6 | 🔵 | `CheckResult` no preparado para L2/L3/L4 | Aceptado–ADR (se resuelve con `VerificationOutcome`) | [#19](https://github.com/Juliohes/Autoken-facturas/issues/19) | abierto |

## 2. Código — Tests

| ID | Sev | Hallazgo | Respuesta | Issue | Estado |
|---|---|---|---|---|---|
| TST-1 | 🔴 | Ramas del CIF letra-vs-dígito sin probar | Aceptado–corregir | [#20](https://github.com/Juliohes/Autoken-facturas/issues/20) | abierto |
| TST-2 | 🔴 | Rama "no reconocido" del dispatcher sin probar | Aceptado–corregir | [#20](https://github.com/Juliohes/Autoken-facturas/issues/20) | abierto |
| TST-3 | 🟠 | Fronteras de tolerancia (0,02/0,03) sin probar | Aceptado–corregir (boundary tests) | [#20](https://github.com/Juliohes/Autoken-facturas/issues/20) | abierto |
| TST-4 | 🟠 | Los tests de fallo no asertan `.reason` (mensaje al usuario) | Aceptado–corregir | [#20](https://github.com/Juliohes/Autoken-facturas/issues/20) | abierto |
| TST-5 | 🟠 | `CorrelationIdMiddleware` sin test unitario | Aceptado–corregir | [#22](https://github.com/Juliohes/Autoken-facturas/issues/22) | abierto |
| TST-6 | 🟡 | Sin cobertura de **ramas** en CI (`pytest-cov --cov-branch`) | Aceptado–corregir (quality gate) | [#22](https://github.com/Juliohes/Autoken-facturas/issues/22) | abierto |
| TST-7 | 🟥 | El gate de aislamiento es `assert True` (gate bloqueante que miente) | Aceptado–corregir (test real concurrente o `xfail` razonado) | [#22](https://github.com/Juliohes/Autoken-facturas/issues/22) | abierto |

## 3. Código — Seguridad

| ID | Sev | Hallazgo | Respuesta | Issue | Estado |
|---|---|---|---|---|---|
| SEC-1 | 🟠 | Contraseña por defecto `autoken` versionada | Aceptado–corregir (secure defaults) | [#23](https://github.com/Juliohes/Autoken-facturas/issues/23) | abierto |
| SEC-2 | 🟡 | `X-Correlation-ID` entrante sin sanear | Aceptado–corregir (regex en el borde) | [#23](https://github.com/Juliohes/Autoken-facturas/issues/23) | abierto |
| SEC-3 | 🟡 | `/docs` y `/health` abiertos en prod (filtran version/environment) | Aceptado–corregir | [#23](https://github.com/Juliohes/Autoken-facturas/issues/23) | abierto |
| SEC-4 | 🟡 | Audits de deps no bloquean + sin lockfile backend | Aceptado–diferir (infra) | [#24](https://github.com/Juliohes/Autoken-facturas/issues/24) | abierto |
| SEC-5 | 🔵 | gitleaks bajado por curl sin checksum; Actions por tag flotante | Aceptado–diferir (infra) | [#24](https://github.com/Juliohes/Autoken-facturas/issues/24) | abierto |
| SEC-6 | 🔵 | Redis sin auth; sin security headers; sin rate limiting | Aceptado–diferir (infra) | [#24](https://github.com/Juliohes/Autoken-facturas/issues/24) | abierto |

## 4. Diseño — Arquitectura

| ID | Sev | Hallazgo | Respuesta | Issue | Estado |
|---|---|---|---|---|---|
| ARQ-1 | 🔴 | RLS+pooling: fuga de contexto de tenant entre peticiones | Aceptado–ADR (ADR-0001 ampliado) + test concurrente | [#17](https://github.com/Juliohes/Autoken-facturas/issues/17) | abierto |
| ARQ-2 | 🔴 | Idempotencia del job OCR ausente del diseño | Aceptado–ADR/corregir (`file_hash + engine`) | [#21](https://github.com/Juliohes/Autoken-facturas/issues/21) | abierto |
| ARQ-3 | 🔴 | Camino cross-tenant de `platform_admin` rompe el modelo RLS | Aceptado–ADR (antes de Sprint 4; sin `BYPASSRLS` en la app) | — (ADR pendiente) | diferido |
| ARQ-4 | 🟠 | Doble política RLS "según rol" sin especificar (fail-closed) | Aceptado–ADR (ADR-0001 ampliado) | [#17](https://github.com/Juliohes/Autoken-facturas/issues/17) | abierto |
| ARQ-5 | 🟠 | Frontera async del upload difusa (ClamAV en request vs worker) | Aceptado–diferir (bloquea S2.1) | — (S2.1) | diferido |
| ARQ-6 | 🟠 | L3 (AEAT/VIES) frágil: fijar que corre en el worker, no bloquea botón | Aceptado–ADR (ADR-0011) | [#19](https://github.com/Juliohes/Autoken-facturas/issues/19) | abierto |
| ARQ-7 | 🟠 | El "árbitro por campo" es prosa, no contrato (función pura) | Aceptado–diferir (Fase 1, 2º motor) | — (Fase 1) | diferido |
| ARQ-8 | 🟠 | Frontera `ocr` ↔ `invoice_intake` sin contratar (acoplamiento) | Aceptado–ADR (evento `OcrCompleted`, antes de Sprint 2) | — (ADR pendiente) | diferido |
| ARQ-9 | 🟠 | Único dominio de fallo (backup ≠ disponibilidad): declarar RTO/RPO | Aceptado–ADR (enmienda ADR-0005) | — (ADR pendiente) | diferido |
| ARQ-10 | 🟡 | Semántica del bus `shared/events` (in-process vs Redis) | Aceptado–diferir (S2) | — (S2) | diferido |
| ARQ-11 | 🟡 | CQRS-light: no sobre-ingenierizar | Aceptado (nota de diseño) | — | nota |
| ARQ-12 | 🟡 | Portabilidad AWS "sin reescritura" optimista (Caddy on-demand TLS) | **EN DECISIÓN (Julio)** — matiza ADR-0005 / plan línea 223 | — | decisión pendiente |
| ARQ-13 | 🟡 | Cifrado por tenant (S5) afecta al esquema de S1: decidir alcance ya | Aceptado–ADR (ADR de datos) | [#18](https://github.com/Juliohes/Autoken-facturas/issues/18) | abierto |

## 5. Diseño — Patrones

| ID | Sev | Hallazgo | Respuesta | Issue | Estado |
|---|---|---|---|---|---|
| PAT-1 | 🟢 | Result/Outcome enriquecido (`VerificationOutcome`) — contrato base | Aceptado–ADR (ADR-0011) | [#19](https://github.com/Juliohes/Autoken-facturas/issues/19) | abierto |
| PAT-2 | 🟢 | Strategy + Factory de motores OCR | **Ya cubierto (parcial)** por `OcrEngine` Protocol + base (PR #15) | [#19](https://github.com/Juliohes/Autoken-facturas/issues/19) | en curso |
| PAT-3 | 🟢 | Ports & Adapters / functional core (declararlo y protegerlo) | Aceptado–ADR (ADR-0011 / pipeline) | [#19](https://github.com/Juliohes/Autoken-facturas/issues/19) | abierto |
| PAT-4 | 🟡 | Chain of Responsibility (CIF L1→L2→L3→L4) | Aceptado–ADR (diseñar ADR-0011, implementar S2.8) | [#19](https://github.com/Juliohes/Autoken-facturas/issues/19) | abierto |
| PAT-5 | 🟡 | Adapter de fuentes externas (timeout/caché/CB en el puerto) | Aceptado–ADR (ADR-0011) | [#19](https://github.com/Juliohes/Autoken-facturas/issues/19) | abierto |
| PAT-6 | 🟡 | Repository + tenant-context dependency (punto único del `SET`) | Aceptado–ADR (ADR-0001 ampliado) | [#17](https://github.com/Juliohes/Autoken-facturas/issues/17) | abierto |
| PAT-7 | 🟡 | Pipeline funcional (NO Template Method) + árbitro puro | Aceptado–diferir (Fase 1/S2) | — | diferido |
| PAT-8 | 🟡 | Domain Events in-process (S2, síncrono, no Redis) | Aceptado–diferir (S2) | — (S2) | diferido |
| PAT-9 | 🟡 | CQRS-light en `reporting/` (S3) | Aceptado–diferir (S3) | — (S3) | diferido |
| AP-* | 🟢 | Anti-patrones bajo vigilancia (God Object en `process_invoice`) | Aceptado (BUILD-RISK a vigilar en S2.3) | [#21](https://github.com/Juliohes/Autoken-facturas/issues/21) | nota |

## 6. Diseño — Modelo de datos / BD

| ID | Sev | Hallazgo | Respuesta | Issue | Estado |
|---|---|---|---|---|---|
| BD-1 | 🔴 | FK no garantizan confinamiento de tenant → FK compuestas | Aceptado–ADR (ADR-0001 ampliado) | [#17](https://github.com/Juliohes/Autoken-facturas/issues/17) | abierto |
| BD-2 | 🔴 | `cif_lookups` global filtra cartera de proveedores (side-channel) | Aceptado–ADR (modelo de amenaza) | [#18](https://github.com/Juliohes/Autoken-facturas/issues/18) | abierto |
| BD-3 | 🔴 | Alcance de unicidad de `file_hash_sha256` sin definir | Aceptado–ADR (`UNIQUE(tenant_id, file_hash)`) | [#18](https://github.com/Juliohes/Autoken-facturas/issues/18) | abierto |
| BD-4 | 🟠 | Estrategia de PK no decidida (IDOR) → UUIDv7 | Aceptado–ADR | [#18](https://github.com/Juliohes/Autoken-facturas/issues/18) | abierto |
| BD-5 | 🟠 | Snapshot de contraparte vs `counterparties` (deriva) | Aceptado–ADR (snapshot + FK opcional) | [#18](https://github.com/Juliohes/Autoken-facturas/issues/18) | abierto |
| BD-6 | 🟠 | Faltan CHECK constraints; enums como texto libre | Aceptado–diferir (S1.1 DDL) | — (S1.1) | diferido |
| BD-7 | 🟠 | `audit_log` append-only sub-especificado (hash-chain + partición) | Aceptado–ADR (ADR de datos) | [#18](https://github.com/Juliohes/Autoken-facturas/issues/18) | abierto |
| BD-8 | 🟠 | PKs implícitas en tablas hijas (duplicados silenciosos) | Aceptado–diferir (S1.1 DDL) | — (S1.1) | diferido |
| BD-9 | 🟡 | JSONB sin estrategia de índice | Aceptado–diferir (S1.1) | — | nota |
| BD-10 | 🟡 | TTL de `cif_lookups` sin purga | Aceptado–diferir (S2.8) | — (S2.8) | diferido |
| BD-11 | 🟡 | `timestamptz` siempre; faltan `created_at`/`updated_at` | Aceptado–corregir (convención DDL) | — (S1.1) | diferido |
| BD-12 | 🟡 | RLS/`REVOKE` en migraciones con downgrade simétrico | Aceptado–ADR (ADR-0001 ampliado) | [#17](https://github.com/Juliohes/Autoken-facturas/issues/17) | abierto |
| BD-13 | 🔵 | Nits de unicidad (`slug`, `companies.cif` por tenant, etc.) | Aceptado–diferir (S1.1 DDL) | — | nota |

---

## Mapa hallazgo → ADR

| ADR | Cubre | Issue |
|---|---|---|
| **ADR-0001 ampliado** (RLS) | ARQ-1, ARQ-4, BD-1, BD-12, PAT-6 | [#17](https://github.com/Juliohes/Autoken-facturas/issues/17) |
| **ADR nuevo (datos)** | BD-2, BD-3, BD-4, BD-5, BD-7, ARQ-13 | [#18](https://github.com/Juliohes/Autoken-facturas/issues/18) |
| **ADR-0011 (contraparte)** | PAT-1/3/4/5, ARQ-6, BP-6 | [#19](https://github.com/Juliohes/Autoken-facturas/issues/19) |
| ADR `platform_admin` (Sprint 4) | ARQ-3 | — |
| ADR eventos `ocr`→`invoice_intake` (Sprint 2) | ARQ-8, PAT-8 | — |
| Enmienda ADR-0005 (RTO/RPO) | ARQ-9 | — |

---

## Decisiones que requieren tu visto bueno (Julio)

> Regla acordada: no se elimina nada del plan salvo que un hallazgo lo contradiga, y en ese caso se
> pregunta antes. Solo hay **un** punto así:

### ARQ-12 — Portabilidad a AWS "sin reescritura"
- **Dónde:** PLAN MAESTRO §"Infra" (≈línea 223): *"Migrable a cualquier proveedor (AWS incluido) sin
  reescritura"* y ADR-0005 (*"portable a AWS"*).
- **Hallazgo:** el claim es optimista. **Caddy on-demand TLS** (HTTPS automático por subdominio de tenant)
  **no tiene equivalente directo en AWS ALB/ACM**; migrar exigiría rediseñar la terminación TLS.
- **Opciones:**
  1. **Matizar el texto** (recomendado): cambiar "sin reescritura" por *"portable con adaptación de la capa
     TLS/ingress (Caddy on-demand TLS no tiene equivalente directo en ALB)"*. **Aditivo, no borra la decisión.**
  2. Dejarlo como está y registrar la salvedad solo aquí (en este plan de remediación).
  3. Otra redacción que prefieras.
- **Estado:** *decisión pendiente* — no toco el plan hasta tu confirmación.

---

## Plan de ataque (orden recomendado por la auditoría)

1. **Antes de Sprint 1** — tres ADRs baratos: [#17](https://github.com/Juliohes/Autoken-facturas/issues/17)
   (RLS), [#18](https://github.com/Juliohes/Autoken-facturas/issues/18) (datos),
   [#19](https://github.com/Juliohes/Autoken-facturas/issues/19) (contraparte/ADR-0011).
2. **Valor actual** — endurecer `verification.py` con Bug-First TDD: [#20](https://github.com/Juliohes/Autoken-facturas/issues/20).
3. **Correcciones rápidas** — [#23](https://github.com/Juliohes/Autoken-facturas/issues/23) (Depends, secure
   defaults, saneado) + quality gates [#22](https://github.com/Juliohes/Autoken-facturas/issues/22).
4. **Al nacer el worker (S2.3)** — idempotencia: [#21](https://github.com/Juliohes/Autoken-facturas/issues/21).
5. **Infra** — hardening supply-chain: [#24](https://github.com/Juliohes/Autoken-facturas/issues/24).
</content>

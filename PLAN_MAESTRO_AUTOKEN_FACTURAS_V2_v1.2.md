# PLAN MAESTRO — Autoken Facturas v2 (Setex v2)
**Plataforma SaaS multi-asesoría de digitalización de facturas con OCR/IA**
Versión **1.2 — 18/06/2026** (base v1.1 del 11/06/2026; **solo añadidos, no se elimina nada del plan inicial**) — Documento de ejecución para Claude Code, supervisado por Julio
**v1.1: datos de arranque confirmados (GitHub, dominio, VPS, emails, cuentas IA) — listo para ejecutar**
**v1.2 (Enmienda 2026-06-18, Fase 0 cerrada, antes de Fase 1)**: incorporada la mejora crítica del **CIF de la
contraparte** e **identidad propia conocida** (no se lee por OCR lo que ya se sabe del registro). Decisión nueva
en **§11.8** (con investigación de mercado), refuerzos en **§3.6** (reglas 10-13), **§3.4** (modelo de datos),
**S2.3/S2.4/S2.8** (tareas) y **§9** (pendientes de Julio). ADR-0011 (§11.1). Cambio **aditivo**: no rompe nada.

---

## 0. RESUMEN EJECUTIVO

Reconstrucción completa de la aplicación Setex Facturas (v1, Node.js, monolito sin prácticas) como **plataforma multi-tenant white-label** en Python/FastAPI + React PWA, vendible a N asesorías, con:

- Aislamiento total de datos entre asesorías (PostgreSQL Row-Level Security de dos niveles + buckets separados + cifrado por tenant).
- Frontend **visualmente idéntico al actual** (los usuarios de Setex no deben notar el cambio), con theming por asesoría.
- Pipeline OCR profesional de 4 capas con regla anti-alucinación.
- Panel de plataforma (Julio + Alberto) para alta/demo/gestión de asesorías en minutos.
- Dos entornos: VPS producción + VPS staging (Hostinger), todo en Docker Compose.
- GitHub con gitflow, Conventional Commits, CI obligatorio y trazabilidad total.
- Carril paralelo futuro: Verifactu + factura electrónica B2B + paquete legal (NO bloquea el MVP).

---

## 0-BIS. DATOS CONFIRMADOS DE ARRANQUE (fuente de verdad)

| Dato | Valor confirmado |
|---|---|
| GitHub | Usuario `Juliohes` (juliohesuni@gmail.com) — Repo privado: **`Juliohes/Autoken-facturas`** |
| Colaboradores | Alberto sin cuenta GitHub aún → tarea opcional: invitarlo cuando la cree (rol: write, no admin) |
| Dominio | **`autoken.es`** (YA comprado). NO se compra ningún dominio nuevo. Estrategia: subdominios de primer nivel (ver 3.3-bis) |
| VPS A (actual) | `72.60.186.89` — Ubuntu 24.04, KVM 2, 100 GB. **Hoy ejecuta la v1 de Setex. NO SE TOCA** hasta retirada de v1. Tras retirada → se limpia y pasa a STAGING |
| VPS B (nuevo) | `2.24.8.109` — Ubuntu 24.04 LTS, KVM 2, 100 GB. **Aquí se construye la v2 (hace de staging durante el desarrollo) y aquí nace PRODUCCIÓN en el go-live** |
| Admins plataforma | 2 cuentas personales con 2FA: `juliohesuni@gmail.com` (Julio) y `albertomurimarti@gmail.com` (Alberto). **`soporte@autoken.es` NO es cuenta de login**: es el remitente del sistema y buzón de soporte (decisión de seguridad: sin cuentas admin compartidas, para que el audit log identifique siempre a la persona) |
| Email remitente sistema | `soporte@autoken.es` (pendiente: Julio confirma con Alberto y obtiene credenciales SMTP — ver PDF guía, paso 6) |
| Branding Setex | Logo y colores se extraen de la v1 (icono de pantalla "SETEX" naranja/blanco sobre fondo oscuro). Tarea D.2 incluye extracción de assets y hex exactos desde el código/recursos de la v1 |
| Tenant demo | "Asesoría José Ramón" — slug `joseramon` (nombre provisional, renombrable desde el panel) |
| Cuentas IA | Azure: **ya existe** (crear recursos Document Intelligence + Azure OpenAI, región UE). Mistral: crear cuenta para el POC. NOTA: ChatGPT Pro y Claude Max son suscripciones de consumidor, NO sirven como API |
| Disponibilidad Julio | Total (dedicación completa al proyecto) → calendario del plan: ritmo full-time (~10-12 semanas hasta go-live) |
| Facturas POC | Las 4+ actuales en la v1 de Setex y creciendo a diario → tarea 1.1 incluye exportarlas desde la v1 |
| Ventana de migración | Nocturna (Setex no usa la app de noche) |

⚠️ **Nota de seguridad sobre los VPS**: actualmente tienen login root por contraseña. La tarea 0.3 lo elimina (usuario no-root + solo clave SSH + root deshabilitado) y **rota la contraseña root** por haber circulado fuera del gestor de secretos. Hasta entonces, no compartir esa contraseña en ningún chat, email o documento.

---

## 1. REGLAS DE ORO PARA CLAUDE CODE (innegociables)

1. **Supervisión**: Julio aprueba el plan de cada sprint antes de escribir código. Dentro del sprint, Claude Code trabaja en autonomía tarea a tarea.
2. **Commits atómicos**: un commit por tarea completada con sus tests en verde. JAMÁS commits gigantes mezclando temas.
3. **Nada se mergea a `develop` con CI en rojo.** Nada se mergea a `main` sin tag de release.
4. **Anti-alucinación de la IA de OCR**: campo no legible = `null` + aviso visual. Prohibido que un valor inventado llegue a la UI como si fuera leído.
5. **Anti-cruce de tenants**: la suite de tests de aislamiento (sección 8) es un gate de CI. Si falla, el build se rompe. Sin excepciones.
6. **Sin secretos en el repo**: `.env` en `.gitignore` desde el commit 1; secretos vía variables de entorno + `doppler`/`sops`. Pre-commit hook con `gitleaks`.
7. **Staging nunca contiene datos reales de clientes.**
8. **Código completo**: nunca `...` ni TODOs silenciosos. Si algo queda pendiente, se crea issue en GitHub.
9. **Documentar decisiones**: toda decisión arquitectónica nueva → ADR en `docs/adr/NNN-titulo.md`.
10. **Idioma**: código e identificadores en inglés; comentarios de dominio, ADRs y documentación en español.

---

## 2. GIT, GITHUB Y TRAZABILIDAD

### 2.1 Repositorio
- Repo privado: **`Juliohes/Autoken-facturas`** (monorepo: `backend/`, `frontend/`, `infrastructure/`, `docs/`).
- `README.md` con quickstart; `docs/` con arquitectura, ADRs, runbooks.

### 2.2 Ramas (gitflow adaptado a equipo pequeño)
| Rama | Propósito | Protección |
|---|---|---|
| `main` | Solo código desplegado en producción | Protegida: merge solo desde `release/*` o `hotfix/*`, con tag |
| `develop` | Integración continua; se despliega a staging automáticamente | Protegida: merge solo por PR con CI verde |
| `feature/<id>-<slug>` | Una rama por tarea del plan (ej. `feature/S2.3-blur-detection`) | Se borra tras merge |
| `release/vX.Y.Z` | Congelación para release; solo fixes | — |
| `hotfix/vX.Y.Z+1` | Urgencias sobre producción | Merge a `main` Y a `develop` |

### 2.3 Conventional Commits (obligatorio)
Formato: `tipo(ámbito): descripción` — ej.: `feat(ocr): blur detection cliente con varianza de Laplaciano`
Tipos: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`, `perf`, `security`.
Ámbitos: `tenancy`, `identity`, `intake`, `ocr`, `companies`, `platform`, `reporting`, `frontend`, `infra`, `verifactu`.

### 2.4 Tags y vuelta atrás
- Tag semántico en cada release: `v2.0.0`, `v2.1.0`...
- Tag de hito al cerrar cada sprint: `sprint-1-done`, `sprint-2-done`...
- **Vuelta atrás garantizada**: cada tag + migraciones Alembic reversibles (`downgrade` implementado y testeado) + backup de BD previo a cada deploy. Volver a un punto = `git checkout <tag>` + `alembic downgrade` + restore si aplica. Documentado en `docs/runbooks/rollback.md`.

### 2.5 CI/CD (GitHub Actions)
Pipeline en cada PR a `develop`:
1. Lint (`ruff`, `eslint`) + tipos (`mypy`, `tsc`).
2. Tests unitarios + integración (PostgreSQL y Redis en servicios del workflow).
3. **Suite de aislamiento multi-tenant (gate bloqueante).**
4. `gitleaks` (secretos) + `pip-audit`/`npm audit` (dependencias vulnerables).
5. Build de imágenes Docker.

Pipeline en merge a `develop`: deploy automático a **staging**.
Pipeline en tag `v*` sobre `main`: deploy a **producción** con aprobación manual (environment protegido de GitHub).

---

## 3. ARQUITECTURA (referencia de decisiones ya cerradas + delta multi-asesoría)

### 3.1 Stack
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, PostgreSQL 16, Redis 7, arq (jobs), MinIO (ficheros), Caddy 2 (TLS).
- **Frontend**: React 18 + Vite + TypeScript, TanStack Query, Tailwind, shadcn/ui, PWA (vite-plugin-pwa), cliente API autogenerado desde OpenAPI.
- **Observabilidad**: structlog (JSON + correlation id), Sentry, Grafana Cloud Free.
- **Seguridad base**: FastAPI-Users + Argon2id, JWT corto + refresh con rotación, slowapi, secweb, UFW, fail2ban, Cloudflare Free.

### 3.2 Estructura del backend (monolito modular, Screaming Architecture)
```
backend/src/
├── tenancy/            # NÚCLEO multi-asesoría: Tenant, branding, middleware subdominio, RLS
├── security/           # auth, rbac (rol × tenant), audit log inmutable, rate limit
├── identity/           # usuarios, registro+aprobación, memberships (user ↔ company)
├── companies/          # empresas cliente de cada asesoría (CRUD, import Excel)
├── invoice_intake/     # DDD completo: facturas recibidas/emitidas vía OCR (núcleo)
├── ocr/                # DDD completo: pipeline extracción, motores, validación, dataset mejora
├── invoicing/          # FUTURO (carril Verifactu): emisión formal — solo esqueleto + ADR
├── verifactu/          # FUTURO: hash chain, QR, AEAT — solo esqueleto + ADR
├── platform_admin/     # panel Julio+Alberto: alta tenants, branding, demo, métricas, consumo
├── reporting/          # CQRS-light: queries paneles, export Excel
├── notifications/      # stub MVP: emails de aprobación de registro (SMTP)
├── jobs/               # workers arq: ocr_worker, cleanup, backups
├── shared/             # db, config (pydantic-settings), excepciones, eventos internos
└── main.py
```

### 3.3 Jerarquía de tenancy y roles
```
Plataforma (platform_admin: juliohesuni@gmail.com y albertomurimarti@gmail.com — 2FA obligatorio; sin cuentas compartidas)
└── Tenant = Asesoría (tenant_admin: dueños de la asesoría — ven TODO su tenant)
    └── Company = Empresa cliente (user: empleados/autónomos — ven SOLO su empresa)
```
- Resolución de tenant por subdominio (`<slug>.autoken.es`) en middleware; fija `SET app.tenant_id` y `app.company_id` como variables de sesión PostgreSQL.
- RLS con `FORCE ROW LEVEL SECURITY` en TODAS las tablas de negocio, política doble (`tenant_id`, `company_id`) según rol. El usuario de BD de la app NO es owner ni superusuario.
- JWT incluye `tenant_id`; si no coincide con el subdominio → 403.
- `platform_admin` accede vía `panel.autoken.es` con rol propio; sus accesos a datos de tenants quedan en audit log.

### 3.3-bis Estrategia de dominios (DECISIÓN CERRADA — ADR-004)
- **Un solo dominio: `autoken.es`**, con subdominios de PRIMER nivel. No se compra `autoken.es`.
- Mapa: `setex.autoken.es` (app Setex) · `joseramon.autoken.es` (demo) · `<asesoria>.autoken.es` (futuras) · `panel.autoken.es` (plataforma) · `setex-staging.autoken.es` y `panel-staging.autoken.es` (staging) · `autoken.es` y `www.autoken.es` quedan LIBRES para la web corporativa.
- **Por qué subdominios y NO rutas (`autoken.es/facturas/...`)**: (1) el aislamiento multi-tenant se resuelve por host, no por path — cookies, CORS y CSP quedan separados por asesoría; (2) el certificado gratuito de Cloudflare solo cubre un nivel (`*.autoken.es`), que es exactamente lo que usamos; (3) futuras apps = más subdominios (`crm.autoken.es`, `app2.autoken.es`) sin tocar nada de facturas. Las rutas acoplarían todos los productos a un mismo origen y romperían el modelo de seguridad.
- `setex-facturas.es` (dominio actual de la v1) se mantiene como **dominio personalizado** del tenant Setex → sus usuarios no cambian de URL.

### 3.4 Modelo de datos núcleo (tablas principales)
| Tabla | Campos clave | Notas |
|---|---|---|
| `tenants` | id, slug, name, custom_domain, is_demo, status, created_at | slug = subdominio |
| `tenant_branding` | tenant_id, logo_url, color_primary, color_secondary, app_name, favicon | theming runtime |
| `companies` | id, tenant_id, name, cif, status(active/pending), notes | import desde Excel |
| `users` | id, tenant_id, email, password_hash, role, status(pending/active), totp_secret | aprobación admin |
| `memberships` | user_id, company_id, tenant_id | un user puede pertenecer a N empresas |
| `invoices` | id, tenant_id, company_id, uploaded_by, type(received/issued), is_test, status, invoice_number, issue_date, supplier_name, supplier_cif, receiver_name, receiver_cif, total, file_key, file_hash_sha256, confirmed_by, confirmed_at | `file_hash` para duplicados |
| `invoice_tax_lines` | invoice_id, iva_pct, base, cuota | tramos de IVA (ya existe en v1) |
| `invoice_irpf` | invoice_id, pct, cuota | solo si aparece en el documento |
| `ocr_extractions` | invoice_id, engine, raw_json(JSONB), field_confidences(JSONB), duration_ms, cost | una fila por motor |
| `ocr_corrections` | invoice_id, field, ai_value, human_value, corrected_by, at | **dataset de mejora continua** |
| `audit_log` | id, tenant_id, actor_id, action, entity, entity_id, payload_hash, at | append-only, sin UPDATE/DELETE |
| `counterparties` (NUEVO 2026-06-18, §11.8) | id, tenant_id, cif, name, name_source(human/aeat/vies/borme/commercial), verified_at, times_seen | **supplier master** del tenant: CIF↔razón social ya confirmados; primera línea de verificación del CIF de contraparte |
| `cif_lookups` (NUEVO 2026-06-18, §11.8) | cif, source, exists(bool), official_name, raw_json(JSONB), fetched_at, ttl | **caché global** de resoluciones externas (AEAT/VIES/BORME) para no repetir llamadas ni gastar cuota |

> `invoices` (NUEVO 2026-06-18, §11.8): añadir `counterparty_cif_status` (valid/invalid/not_found/unverified),
> `counterparty_name_match` (match/mismatch/unknown), `counterparty_official_name`, `counterparty_source`.
> El CIF/nombre del usuario (`supplier_*` o `receiver_*` según el tipo) se **inyecta desde `companies`**, no del OCR.

Toda tabla de negocio: índice compuesto que empieza por `tenant_id`. (`cif_lookups` es caché global no-tenant:
es dato público de registro, sin información de cliente; no lleva `tenant_id` ni RLS.)

### 3.5 Ficheros (MinIO)
- Bucket por tenant: `invoices-<tenant_id>`. Original SIEMPRE conservado (imagen/PDF) + versión procesada.
- Antivirus ClamAV + validación de MIME real + límite de tamaño en el upload.
- Hash SHA-256 del fichero → detección de duplicados (regla ya existente en v1, se conserva).

### 3.6 Reglas de negocio confirmadas de la v1 (se conservan todas)
1. Selector Recibida/Emitida ANTES de capturar.
2. El CIF del usuario debe aparecer en la factura (como receptor si es recibida, como emisor si es emitida). Si no aparece → aviso bloqueante. Excepción: admins (tenant y plataforma). **Matización 2026-06-18 (§11.8)**: el nombre y CIF de la **propia empresa** del usuario NO se "leen" para rellenar campos: se **conocen** desde el registro (tabla `companies`) y se inyectan. El OCR de "su lado" solo sirve para confirmar que la foto es de SU factura (anti-foto-equivocada) y detectar contradicciones con el selector Recibida/Emitida.
3. Facturas de prueba de admins: flag `is_test`, excluidas de informes, purga con un clic.
4. Aviso de duplicado (hash + heurística nº factura + CIF + fecha + total).
5. Validación aritmética: Σ(base×IVA%) = cuota por tramo, Σ tramos + IVA − IRPF = total. Descuadre → aviso "Revisar".
6. Validación de dígito de control de CIF/NIF (algoritmo oficial, determinista).
7. Confirmación humana obligatoria con todos los campos editables ANTES de guardar.
8. **NUEVO**: checkbox "He revisado que los datos coinciden con la factura — la veracidad de los datos es responsabilidad de quien los confirma" + registro en audit_log (quién, cuándo, snapshot de datos).
9. Panel admin asesoría: filtros (fechas, proveedor/CIF, usuario, estado), tabla completa (tramos IVA, IRPF, totales, estado, imagen "Ver", fecha subida), export Excel, edición de campos (auditada), gestión de empresas (alta/pendiente/activa) y aprobación de usuarios.
10. **NUEVO (2026-06-18, §11.8) — Foco del OCR en lo que sí importa**: los campos de oro que la IA debe leer son **fecha**, **importes** (total + tramos) y, sobre todo, el **CIF de la CONTRAPARTE** (proveedor si recibida, cliente si emitida). El CIF de la contraparte es el campo que más falla y el más crítico contablemente: recibe verificación reforzada (regla 11).
11. **NUEVO (2026-06-18, §11.8) — Verificación del CIF de la contraparte en 4 niveles**: (L1) estructura/ dígito de control módulo-23 [ya implementado en `ocr/verification.py`]; (L2) **supplier master** del tenant (si el CIF ya se confirmó antes, se reutiliza su razón social); (L3) **resolución externa CIF→nombre + existencia** (AEAT censal / VIES / BORME) y comparación con el nombre leído por la IA; (L4) caché de resoluciones. Resultado: **CIF inválido o inexistente → bloqueo**; **CIF existe pero el nombre no coincide → aviso mostrando la razón social oficial**.
12. **NUEVO (2026-06-18, §11.8) — Pantalla de revisión con jerarquía**: todos los campos van **plegados en un desplegable comprimido** EXCEPTO **tres siempre visibles**: **importe total**, **CIF de la contraparte** y **fecha**. El botón **"Confirmar y guardar" se BLOQUEA** si el CIF de la contraparte es inválido/inexistente o si el CIF propio leído contradice el CIF conocido del usuario. Bajo el botón, **aviso en rojo, grande y legible**: *"Revisa bien los datos antes de confirmar: su veracidad es responsabilidad de quien los confirma."* (complementa, no sustituye, el checkbox de la regla 8).
13. **NUEVO (2026-06-18, §11.8)**: toda resolución/validación del CIF de contraparte (fuente consultada, veredicto, nombre oficial devuelto) se registra junto a la factura y alimenta el `supplier master` y `ocr_corrections` (mejora continua).

---

## 4. PIPELINE OCR PROFESIONAL (4 capas) — el corazón del producto

### Capa 1 — Captura guiada en el cliente (PWA)
- Se conserva el marco grande actual como guía visual.
- **Auto-captura tipo banco**: `getUserMedia` + análisis de frames en tiempo real con OpenCV.js:
  - Nitidez: varianza del Laplaciano sobre el frame (umbral calibrado con facturas reales del POC).
  - Encuadre: detección de contorno del documento dentro del marco.
  - Exposición: histograma (ni quemada ni oscura).
  - Cuando los 3 checks pasan N frames seguidos → captura automática + vibración háptica.
- Si el usuario fuerza captura manual y la imagen no pasa los checks → **rechazo inmediato** con mensaje claro ("Imagen borrosa, acerca el móvil y mantenlo quieto") y reintento. La foto mala NUNCA viaja al servidor.
- Recorte + corrección de perspectiva en cliente (warpPerspective) → se sube el documento plano, no la mesa.
- Subida de archivo (imagen/PDF) se mantiene como vía alternativa, con los mismos checks de calidad en servidor.

### Capa 2 — Preprocesado en servidor (worker arq)
- Deskew, recorte fino, normalización de contraste, reescalado a resolución óptima del motor.
- PDF con texto nativo → extracción directa de texto (pdfplumber), SIN OCR (precisión perfecta, coste 0).
- ClamAV + MIME real antes de procesar.

### Capa 3 — Extracción doble motor + árbitro + validación determinista
- **Motor A (primario)**: Azure AI Document Intelligence `prebuilt-invoice` → campos estructurados + confianza por campo + bounding boxes.
- **Motor B (secundario)**: LLM de visión (GPT-4o o equivalente) con prompt estricto: *"Si un campo no es legible con certeza, devuelve null. PROHIBIDO inferir o completar CIFs, nombres o números parcialmente visibles."* Salida JSON validada con pydantic.
- **Candidato POC**: Mistral OCR 3 (≈2 $/1.000 págs, fuerte en tablas) — se evalúa contra A y B con las facturas reales.
- **Árbitro por campo**: coinciden → aceptar; discrepan → gana el que pase validación determinista; ninguno la pasa → campo `null` + marca roja "Revisar".
- **Validación determinista (sin IA)**: dígito de control CIF/NIF, cuadre aritmético de tramos y total, fecha plausible (±2 años), IRPF solo si está literalmente en el documento (caso Alex Distribuciones: nunca más un IRPF fantasma).
- Campos con confianza < umbral → resaltado amarillo en la pantalla de confirmación; campos null → rojo.

### Capa 4 — Mejora continua
- Cada edición humana en la confirmación → fila en `ocr_corrections` (valor IA vs valor humano).
- Job mensual: informe de precisión por campo y por motor → decisión basada en datos (cambiar motor, ajustar prompt, ajustar umbral).
- Las facturas reales del POC + correcciones forman el dataset de evaluación versionado en `docs/ocr-eval/`.

### Coste estimado por factura (orden de magnitud)
Azure prebuilt-invoice ≈ 0,01 €/pág + LLM visión ≈ 0,01-0,02 €/pág → **< 0,04 €/factura**. Se registra el coste real por tenant en `ocr_extractions.cost` (dato para tu pricing).

---

## 5. ENTORNOS E INFRAESTRUCTURA

### 5.1 Asignación de VPS (DECISIÓN CERRADA — ADR-005)
La asignación inicial propuesta por Julio (v2-prod en el VPS de la v1) se **invierte** por seguridad: la máquina que hoy ejecuta la v1 en producción no se toca bajo ningún concepto durante el desarrollo, y producción de la v2 nace en una máquina limpia, 100% Docker, sin herencias.

| Fase | VPS B — `2.24.8.109` (nuevo, KVM 2) | VPS A — `72.60.186.89` (actual, KVM 2) |
|---|---|---|
| Desarrollo (ahora) | Construcción de la v2 + entorno staging (`*-staging.autoken.es`), deploy automático desde `develop` | **Intocable**: sigue sirviendo la v1 de Setex |
| Go-live | **PRODUCCIÓN v2** (`setex.autoken.es`, `panel.autoken.es`, custom `setex-facturas.es`). Staging se apaga temporalmente aquí | v1 en solo-lectura 30 días (red de seguridad y fuente de migración) |
| +30 días | Producción v2 (definitivo) | Se limpia por completo → **STAGING definitivo** |

- Todo en Docker Compose: `caddy`, `api`, `worker`, `postgres`, `redis`, `minio`, `clamav`. Migrable a cualquier proveedor (AWS incluido) sin reescritura.
- Datos: producción = datos reales; staging = SOLO sintéticos/de prueba. Backups: dump PostgreSQL cifrado nocturno + sync MinIO → Hetzner Storage Box (off-site), retención 30d/12m, restore testeado mensualmente.
- Hardening en ambos (tarea 0.3): usuario no-root, SSH solo con clave, root y password-auth deshabilitados, rotación de contraseña root, UFW, fail2ban, unattended-upgrades.
- KVM 2 es suficiente para arrancar; **señal de upgrade** (a KVM 4, unos clics en Hostinger): RAM sostenida > 75% o cola OCR con esperas > 2 min con varias asesorías activas. Se monitoriza en Grafana.
- DNS en Cloudflare (proxy activado): `*.autoken.es` → VPS B; registros de staging apuntando donde corresponda en cada fase.

---

## 6. FASES Y SPRINTS (tareas atómicas con criterio de aceptación y commit)

> Formato: **ID. Tarea** — Criterio de aceptación (CA) — rama `feature/<ID>-slug`, merge por PR a `develop`.
> Al cerrar cada sprint: tag `sprint-N-done` + demo a Julio + aprobación antes del siguiente.

### FASE 0 — Fundación (≈ 3-5 días)
- **0.1 Repo GitHub** — CA: repo privado creado, README, .gitignore, estructura de carpetas, protección de ramas `main`/`develop`, plantillas de PR e issues.
- **0.2 DNS de `autoken.es` en Cloudflare** — CA: zona creada en Cloudflare, nameservers cambiados en el registrador, registros A para `setex`, `panel`, `joseramon`, `setex-staging`, `panel-staging` → `2.24.8.109` (proxy ON). Sin comprar dominios nuevos. (Acción de Julio guiada — PDF paso 3.)
- **0.3 Hardening de los 2 VPS** — CA: en `2.24.8.109` (completo ya) y `72.60.186.89` (SOLO hardening de acceso, sin tocar la v1): usuario no-root `deploy`, SSH solo con clave, `PermitRootLogin no`, `PasswordAuthentication no`, contraseña root rotada, UFW (22/80/443), fail2ban, unattended-upgrades; Docker + Compose instalados en `2.24.8.109`. Runbook en `docs/runbooks/provisioning.md`.
- **0.4 Esqueleto backend** — CA: FastAPI arranca en Docker, healthcheck `/api/v1/health`, structlog, config pydantic-settings, Alembic inicializado.
- **0.5 Esqueleto frontend** — CA: Vite+React+TS+Tailwind arranca, PWA manifest base, cliente OpenAPI autogenerado conectado al healthcheck.
- **0.6 CI completo** — CA: pipeline de la sección 2.5 en verde sobre el esqueleto; gitleaks como pre-commit.
- **0.7 ADRs iniciales** — CA: ADRs 001-006 documentando: multi-tenant RLS 2 niveles, PWA→TWA, pipeline OCR, dominio/subdominios, Hostinger vs AWS, edición de recibidas vs inmutabilidad futura de emitidas.

### FASE 1 — POC OCR con facturas reales (≈ 4-6 días) ⚠️ BLOQUEA EL DISEÑO FINAL DEL MÓDULO `ocr`
- **1.1 Dataset** — CA: 15-30 facturas reales: las 3 aportadas + **exportación de las acumuladas en la v1 de Setex** (crecen a diario; se descargan vía el panel actual o directamente del servidor `72.60.186.89` con permiso de Julio), anotadas a mano con los valores correctos (ground truth) en `docs/ocr-eval/`. Incluir casos difíciles: borrosas, arrugadas, multi-tramo de IVA, con IRPF real y sin IRPF.
- **1.2 Bench motores** — CA: script que pasa el dataset por Azure prebuilt-invoice, GPT-4o visión y Mistral OCR 3; tabla de precisión por campo (nº factura, CIFs, nombres, fecha, tramos, total), coste y latencia. Informe en `docs/ocr-eval/resultado-poc.md`. **Refuerzo 2026-06-18 (§11.8)**: medir de forma **separada y destacada la precisión del CIF de la CONTRAPARTE** (el campo de mayor riesgo); el CIF/nombre propios pueden excluirse del scoring porque se conocen del registro.
- **1.3 Prototipo captura** — CA: página de prueba con auto-captura (blur+encuadre+exposición) funcionando en un móvil Android real; umbral de Laplaciano calibrado con fotos de las facturas del dataset.
- **1.4 Decisión** — CA: Julio aprueba la combinación de motores ganadora. ADR-007.

### SPRINT 1 — Tenancy + Identity + Companies (≈ 1,5-2 semanas)
- **S1.1 Modelo tenants + branding + RLS** — CA: migraciones; políticas RLS FORCE en todas las tablas; test que demuestra que una query sin `app.tenant_id` no devuelve filas.
- **S1.2 Middleware subdominio→tenant** — CA: petición a `demo.localhost` resuelve tenant demo; subdominio inexistente → 404 neutro.
- **S1.3 Auth completa** — CA: login JWT+refresh rotativo, Argon2id, rate limit en login, 2FA TOTP obligatorio para `platform_admin` y opcional para `tenant_admin`.
- **S1.4 Registro con aprobación** — CA: formulario (email, nombre empresa, CIF con validación de dígito de control, contraseña con política), email al tenant_admin, pantalla de aprobación, verificación de email del usuario. Flujo idéntico al actual de cara al usuario.
- **S1.5 Companies + import Excel** — CA: CRUD empresas con estados activa/pendiente, importador del Excel de Setex (51 empresas) con informe de errores.
- **S1.6 RBAC** — CA: matriz de permisos user/tenant_admin/platform_admin testeada endpoint a endpoint.
- **S1.7 Suite anti-cruce v1** — CA: tests automáticos: usuario del tenant A no puede leer/escribir NADA del tenant B en ningún endpoint existente (espera 403/404). Integrada como gate de CI.
- **S1.8 Audit log** — CA: tabla append-only sin permisos de UPDATE/DELETE; toda mutación relevante escribe entrada.

### SPRINT 2 — Intake + OCR (≈ 2-2,5 semanas) — el corazón
- **S2.1 Upload seguro** — CA: subida imagen/PDF a MinIO (bucket por tenant), ClamAV, MIME real, tamaño máx., hash SHA-256, detección de duplicado con aviso.
- **S2.2 Captura guiada PWA** — CA: pantalla de captura idéntica a la actual (marco grande, selector Recibida/Emitida) + auto-captura por frames + rechazo de borrosas + recorte/perspectiva. Probada en Android e iOS reales.
- **S2.3 Worker OCR** — CA: job arq con los motores ganadores del POC en paralelo (asyncio.gather), árbitro por campo, validaciones deterministas, persistencia en `ocr_extractions`. Regla anti-alucinación verificada con test (factura con CIF tapado → campo null, no inventado). **Refuerzo 2026-06-18 (§11.8)**: el CIF/nombre **propios** se inyectan desde `companies` (no se "puntúan" como lectura); el foco de extracción y de enrutado por confianza es fecha + importes + **CIF de contraparte**.
- **S2.4 Pantalla de confirmación** — CA: idéntica a la actual (empresa IA / receptor / fecha / total / tramos IVA editables / IRPF / resumen / Confirmar / Repetir foto) + colores de confianza (amarillo=dudoso, rojo=no leído) + checkbox de responsabilidad + regla "tu CIF debe aparecer en la factura" + descuadres marcados. **Refuerzo 2026-06-18 (§3.6 reglas 11-12, §11.8)**: (a) **3 campos siempre visibles** (total, CIF de contraparte, fecha) y el resto **plegado** en un desplegable; (b) bloque de **veredicto del CIF de contraparte** (válido/ inexistente/ nombre oficial vs leído); (c) botón **"Confirmar y guardar" deshabilitado** si el CIF de contraparte es inválido/inexistente o el CIF propio leído contradice el conocido; (d) **aviso rojo grande** bajo el botón ("Revisa bien los datos… responsabilidad de quien los confirma"). Tests: botón bloqueado en cada condición.
- **S2.8 Verificación del CIF de la contraparte (NUEVO 2026-06-18, §11.8)** — CA: servicio que, dado el CIF de contraparte leído, ejecuta los 4 niveles (estructura → supplier master del tenant → resolución externa AEAT censal/VIES/BORME con caché en `cif_lookups` → comparación de nombre) y devuelve un veredicto estructurado (`valid/invalid/not_found`, `name_match`, `official_name`, `source`). Adaptadores por fuente con interfaz común y *feature flags* por tenant (qué fuentes usar). Cada confirmación humana actualiza el `counterparties` (supplier master). Tests con dobles de las APIs externas (sin red en CI). El **diseño concreto de fuentes y orden** se cierra en **ADR-0011** tras validar disponibilidad de certificado AEAT y coberturas (ver §11.8).
- **S2.5 Persistencia + correcciones** — CA: al confirmar se guarda factura + tramos + snapshot en audit_log; toda edición humana genera filas en `ocr_corrections`.
- **S2.6 Historial usuario** — CA: "Historial de facturas" (últimos 7 días) como en v1.
- **S2.7 Suite anti-cruce v2** — CA: ampliada a facturas y ficheros (usuario A no puede descargar fichero de B ni adivinando la URL de MinIO — URLs firmadas con expiración).

### SPRINT 3 — Panel de asesoría + Reporting (≈ 1-1,5 semanas)
- **S3.1 Panel facturas** — CA: réplica funcional del actual: filtros (fechas, proveedor/CIF, usuario, estado), tabla completa con tramos/IRPF/total/estado/imagen "Ver"/fecha subida, ordenación, paginación por cursor.
- **S3.2 Export Excel** — CA: botón "Descargar Excel" con los filtros aplicados, formato igual al actual.
- **S3.3 Edición auditada** — CA: tenant_admin edita campos; cada cambio queda en audit_log con valor anterior/posterior.
- **S3.4 Gestión empresas y usuarios** — CA: pantalla "Empresas" actual (nueva, eliminar, notas, ver facturas, contador usuarios/facturas/última factura/alta) + aprobación de registros pendientes.
- **S3.5 Facturas de prueba** — CA: flag is_test para capturas de admins, excluidas de informes y export, botón de purga.

### SPRINT 4 — Panel de plataforma + White-label + PWA multi-tenant (≈ 1-1,5 semanas)
- **S4.1 Alta de tenant en minutos** — CA: formulario (nombre, slug, logo, 2 colores) → tenant operativo en `<slug>.autoken.es` sin tocar código ni redesplegar.
- **S4.2 Theming runtime** — CA: frontend carga branding por subdominio (logo, colores como variables CSS, nombre). Setex se ve EXACTAMENTE como hoy.
- **S4.3 Manifest PWA dinámico** — CA: `manifest.json` e iconos servidos por tenant → cada asesoría instala "su" app con su nombre/icono (como los 2 iconos actuales: app cliente y admin). Requisitos TWA listos (HTTPS, service worker, assetlinks preparado).
- **S4.4 Modo demo** — CA: flag is_demo + botón "Crear demo" → tenant con branding del prospecto listo para enseñar en una reunión (primer demo: "Asesoría José Ramón", slug `joseramon`, renombrable); las facturas que se capturen en la demo son reales del prospecto; botón "Convertir a producción" y botón "Purgar demo".
- **S4.5 Métricas y consumo** — CA: panel plataforma muestra por tenant: empresas, usuarios, facturas/mes, coste OCR acumulado, último uso.
- **S4.6 Custom domains** — CA: campo custom_domain + Caddy on-demand TLS; probado apuntando un dominio de prueba.
- **S4.7 Ciclo de vida tenant** — CA: suspender (login bloqueado, datos intactos), exportar (ZIP: BD del tenant + ficheros), borrar (doble confirmación + export previo obligatorio).

### SPRINT 5 — Hardening + QA (≈ 1 semana)
- **S5.1 Cabeceras y límites** — CA: CSP, HSTS, X-Frame-Options, rate limits por endpoint sensible; informe de Mozilla Observatory ≥ A.
- **S5.2 Cifrado por tenant** — CA: campos sensibles cifrados con clave derivada por tenant (pgcrypto/Fernet); rotación documentada.
- **S5.3 Backups + restore drill** — CA: backup nocturno cifrado a Hetzner funcionando; simulacro de restore completo documentado con tiempos.
- **S5.4 Pentest básico propio** — CA: checklist OWASP Top 10 ejecutada (IDOR, inyección, auth, uploads); hallazgos corregidos.
- **S5.5 Pruebas de carga** — CA: k6 con 50 subidas concurrentes de facturas sin degradación inaceptable; cuellos documentados.
- **S5.6 Monitorización y alertas** — CA: Sentry + Grafana con alertas (caída, errores 5xx, cola OCR atascada, disco, certificados).

### FASE DESPLIEGUE — Go-live y migración Setex (≈ 2-4 días)
- **D.1 Release v2.0.0** — CA: `release/v2.0.0` → main + tag; deploy a producción aprobado.
- **D.2 Tenant Setex** — CA: tenant `setex` creado con su branding actual; logo y colores hex extraídos de los recursos de la v1 (icono SETEX naranja/blanco) y validados visualmente por Julio contra las capturas.
- **D.3 Migración de datos (NOCTURNA)** — CA: script idempotente: 51 empresas (Excel) + 4 facturas (datos+ficheros) + usuarios existentes; verificación uno a uno; ventana nocturna; plan de rollback (la v1 sigue viva).
- **D.4 Corte de dominio** — CA: `setex-facturas.es` pasa a apuntar (custom domain) a la v2; v1 queda en solo-lectura 30 días como red de seguridad; usuarios entran con sus mismas credenciales y ven la misma interfaz.
- **D.5 Smoke test con Setex** — CA: un usuario real captura una factura real de punta a punta; Julio verifica panel y export.

### FASE RETIRADA — Limpieza del VPS A (≈ +30 días tras el go-live)
> Se ejecuta cuando la v1 ya no es necesaria (tras los 30 días de solo-lectura) y el VPS A deja de ser
> producción. Hasta entonces el VPS A NO se toca más allá del hardening mínimo ya aplicado (ver ADR-0009).
- **R.1 Hardening completo + limpieza del VPS A `72.60.186.89`** — CA: confirmada la retirada de la v1, parar y
  eliminar los contenedores de la v1 (`setex-prod-*`, `setex-staging-*`, `traefik`), revisar/cerrar el puerto
  `2222` (SSH de contenedor expuesto, hallazgo de la tarea 0.3) y demás puertos no necesarios, y aplicar el
  hardening COMPLETO que se difirió: usuario `deploy` dedicado + `AllowUsers`, `PermitRootLogin no`, UFW
  (con `ufw-docker` si se reinstala Docker), rotación de la contraseña root, y limpieza de usuarios
  preexistentes no necesarios (`devuser`, `claude`, etc., previa confirmación de Julio). Resultado: VPS A
  convertido en **STAGING definitivo**, 100% Docker, sin herencias. Actualizar `docs/runbooks/provisioning.md`.
  **Origen del desvío**: ADR-0009 (hardening mínimo en 0.3 por ser producción activa).

### CARRIL PARALELO (post-MVP, no bloquea nada)
- **P.1 Verifactu** (objetivo: operativo antes de 01/2027): módulo `verifactu` (hash encadenado por empresa emisora, QR, registro de eventos RRSIF, envío AEAT), inmutabilidad de emitidas tras emisión (solo rectificativas), gestión de certificados cifrada por tenant, declaración responsable de Julio como productor de software. Requisito previo: decidir modelo de certificados (cada empresa el suyo vs asesoría como colaborador social) — preguntar a Setex.
- **P.2 Factura electrónica B2B (RD 238/2026)**: export Facturae/UBL + estados de factura. Modelo de datos ya preparado.
- **P.3 Paquete legal**: DPA art. 28 RGPD por asesoría, registro de actividades de tratamiento, avisos legales y privacidad por tenant, residencia UE de subencargados de IA (Azure OpenAI / región UE). Se redacta cuando Julio lo pida.
- **P.4 TWA en Google Play** cuando haya demanda comercial (~1 día).

---

## 7. DEFINITION OF DONE (por tarea)
1. Código completo, tipado y lintado.
2. Tests del caso feliz + errores + (si toca datos) test de aislamiento de tenant.
3. CI verde. PR revisada (auto-revisión documentada de Claude Code + diff legible para Julio).
4. Migraciones con downgrade implementado.
5. Documentación actualizada si cambia comportamiento o arquitectura (ADR si es decisión).
6. Commit(s) con Conventional Commits y referencia al ID de tarea.

## 8. SUITE ANTI-CRUCE DE TENANTS (gate de CI — detalle)
Para CADA endpoint que toque datos:
- Con token del tenant A + recurso del tenant B → 403/404 (nunca 200, nunca datos).
- Con token de user de empresa X + recurso de empresa Y (mismo tenant) → 403/404.
- Sin variable de sesión `app.tenant_id` (acceso directo a BD) → 0 filas (RLS).
- URLs de ficheros firmadas: token caducado o manipulado → 403.
- Test específico: export de tenant A no contiene ni un byte de tenant B.

## 9. LO QUE CLAUDE CODE NECESITA DE JULIO (checklist con estado actual)
> Los pasos detallados de cada ítem pendiente están en **`GUIA_JULIO_PASO_A_PASO.pdf`** (documento hermano de este plan).

- [x] GitHub: usuario `Juliohes` confirmado → Julio crea el repo privado `Autoken-facturas` (PDF paso 1). Alberto: invitar cuando tenga cuenta (opcional, no bloquea).
- [x] Dominio: `autoken.es` ya comprado → mover DNS a Cloudflare (PDF paso 3).
- [x] VPS: `2.24.8.109` (staging→prod) y `72.60.186.89` (v1, futuro staging) identificados → acceso SSH se entrega en la tarea 0.3 (PDF paso 2). ⚠️ Rotar contraseña root tras el hardening.
- [x] **Azure Document Intelligence** ✅ (estado 2026-06-30): recurso `autoken-docintel-we` en **West Europe**; `AZURE_DOCINTEL_ENDPOINT`/`AZURE_DOCINTEL_KEY` en `.env`.
- [x] **Azure OpenAI** ✅ (estado 2026-06-30): recurso `autoken-openai-sweden` (**Sweden Central**) con **`gpt-5.1` desplegado en Data Zone Standard** (NUNCA Global). ⚠️ `gpt-4o`/`gpt-4.1` quedaron **deprecados por Azure** ("deprecating state, cannot be used for new deployments"); se usa **gpt-5.1** (ver §11.3 y §11.10). `AZURE_OPENAI_ENDPOINT`/`AZURE_OPENAI_KEY`/`AZURE_OPENAI_DEPLOYMENT=gpt-5.1` en `.env`.
- [x] **Google Cloud / Vertex** ✅ (NUEVO, estado 2026-06-30): proyecto **`autoken-ocr`** con facturación vinculada; **Vertex AI habilitado** (Google lo renombró a "Agent Platform"/"Gemini Enterprise Agent Platform"; el servicio sigue siendo `aiplatform.googleapis.com`). Cuenta de servicio **`vertex-bench`** (rol *Vertex AI User*) con clave JSON en **`secrets/vertex-sa.json`** (fuera de git). Región **`europe-west4`**. Disponibles: **Gemini 3 Pro / 3.1 Flash** y **Claude (Opus 4.8/4.7, Sonnet 4.6, Fable 5)** sin aceptación de términos aparte.
- [x] **Mistral La Plateforme** ✅ (estado 2026-06-30): cuenta + `MISTRAL_API_KEY` en `.env`.
- [ ] SMTP de `soporte@autoken.es`: confirmar buzón con Alberto y obtener credenciales SMTP del proveedor de correo (PDF paso 6). *(No bloquea Fase 1.)*
- [ ] Excel de las 51 empresas de Setex → carpeta `entregas/` que indicará Claude Code. *(No bloquea Fase 1.)*
- [x] **Facturas reales para el POC** ✅ (estado 2026-06-30): **20 ficheros** en `entregas/facturas/` (14 JPEG de WhatsApp + 4 PNG de capturas + 2 PDF). **Desbloquea el bench (1.2)**.
- [ ] Logo Setex: no hace falta entregar nada — se extrae de la v1 (tarea D.2); si Julio tiene el archivo original (PNG/SVG), mejor: entregarlo.
- [x] **(NUEVO 2026-06-18, §11.8) Certificado electrónico**: **Julio CONFIRMA que dispone de certificado** (2026-06-18) → se usará el servicio **AEAT "Comprobación de NIF de terceros a efectos censales"** como fuente **autoritativa y gratuita** para verificar que el CIF de la contraparte existe y casa con el nombre. Pendiente menor: confirmar si la asesoría puede actuar como colaborador social (ampliaría el uso).
- [x] **(NUEVO 2026-06-18, §11.8) Decisión sobre API comercial de pago** (eInforma/Axesor): **decidida por Julio (2026-06-18)** → se prioriza la **vía gratuita** (supplier master + AEAT censal + VIES + BORME); se contratará una **API de pago de coste bajo SOLO si** no hay forma gratuita de cubrir un caso (p. ej. autónomos no inscritos en el Mercantil y no resueltos por AEAT). Comparar precios en S2.8 antes de contratar.

### 9.1 Mapa de secretos (referencias, NUNCA valores)
| Secreto | Dónde vive |
|---|---|
| `AZURE_DOCINTEL_KEY` / `AZURE_DOCINTEL_ENDPOINT` | GitHub Secrets + `.env` del VPS |
| `AZURE_OPENAI_KEY` / `AZURE_OPENAI_ENDPOINT` | GitHub Secrets + `.env` del VPS |
| `MISTRAL_API_KEY` (solo POC) | GitHub Secrets + `.env` del VPS |
| `GOOGLE_APPLICATION_CREDENTIALS` → JSON de la cuenta de servicio `vertex-bench` | **fichero** en `secrets/vertex-sa.json` del VPS (fuera de git), NUNCA en el repo |
| `SMTP_HOST/USER/PASSWORD` (soporte@autoken.es) | GitHub Secrets + `.env` del VPS |
| `POSTGRES_PASSWORD`, `MINIO_KEYS`, `JWT_SECRET`, claves Fernet por tenant | Generados por Claude Code en el VPS, solo en `.env`/volúmenes cifrados |
| Contraseñas de login de Julio/Alberto | En ningún sitio: se crean en el primer login con 2FA |

## 10. ORDEN DE EJECUCIÓN INMEDIATO
1. Julio completa los pendientes de la sección 9 siguiendo el PDF (≈ 1-2 horas en total).
2. Claude Code ejecuta FASE 0 completa → tag `fase-0-done` → demo a Julio.
3. FASE 1 (POC OCR) → decisión de motores con datos → ADR-007.
4. Sprints 1→5 con aprobación de Julio al cierre de cada uno.
5. Despliegue en `2.24.8.109` + migración nocturna de Setex + corte de `setex-facturas.es`.
6. +30 días: retirada de la v1, limpieza de `72.60.186.89` → staging definitivo (tarea **R.1**).

---

## 11. REGISTRO CENTRAL — fuente única de documentación (REGLA)

> **REGLA (Julio, 2026-06-14)**: TODO lo que se decide, desvía o documenta queda **aquí o enlazado desde aquí**.
> El PLAN MAESTRO es el único sitio donde "se apunta todo". Esta sección se actualiza al cerrar cada tarea y
> cada vez que hay una decisión o desvío. El `CLAUDE.md` es solo el resumen operativo de arranque.

### 11.1 Decisiones arquitectónicas (ADRs) — `docs/adr/`
| ADR | Título | Estado |
|---|---|---|
| **ADR-0001** | Aislamiento multi-tenant con RLS de dos niveles | aceptado |
| **ADR-0002** | PWA primero, TWA (Google Play) cuando haya demanda | aceptado |
| **ADR-0003** | Pipeline OCR de 4 capas (doble motor + árbitro + anti-alucinación) | aceptado |
| **ADR-0004** | Un solo dominio `autoken.es` con subdominios de primer nivel | aceptado (matizado por 0008) |
| **ADR-0005** | Hostinger + Docker Compose; portable a AWS | aceptado (matizado por 0009) |
| **ADR-0006** | Recibidas editables (auditado); emitidas inmutables (futuro Verifactu) | aceptado |
| ADR-0007 | Motores OCR ganadores (tras Fase 1) | pendiente (arquitectura y candidatos decididos 2026-06-15, ver §11.7; ganador tras bench) |
| **ADR-0008** | DNS en Hostinger durante el desarrollo (enmienda a ADR-0004) | aceptado |
| **ADR-0009** | Hardening mínimo del VPS A; construir todo en VPS B | aceptado |
| **ADR-0010** | Capa de verificación determinista "tipo DNI" (dígitos de control CIF/NIF módulo-23, IBAN módulo-97, consulta VIES/AEAT, cuadre aritmético) común a todos los motores | aceptado (2026-06-15) — ⚠️ falta crear el fichero `docs/adr/0010-*.md` (implementado en código) |
| ADR-0011 | Verificación del **CIF de la contraparte** (identidad propia conocida; supplier master + resolución externa AEAT/VIES/BORME) | propuesto 2026-06-18 (ver §11.8; se acepta al cerrar fuentes con datos reales) |

### 11.2 Runbooks — `docs/runbooks/`
| Runbook | Contenido |
|---|---|
| `provisioning.md` | Hardening y acceso de los VPS (tarea 0.3), claves SSH, Docker |
| `rollback.md` | (pendiente) Vuelta atrás: tag + Alembic downgrade + restore |

### 11.3 Desvíos del plan registrados
| Fecha | Desvío | Dónde queda | Tarea de cierre |
|---|---|---|---|
| 2026-06-13 | DNS en Hostinger en vez de Cloudflare (durante desarrollo) | ADR-0008 | Issue #2 (revisar antes del go-live) |
| 2026-06-13 | Proyecto reubicado en `/opt/app-facturas/` (no en `/opt`) | CLAUDE.md | — |
| 2026-06-14 | Tenant demo renombrado `joseramon` → `tuti` | CLAUDE.md / ADR-0008 | — |
| 2026-06-14 | Hardening mínimo del VPS A (es producción activa) | ADR-0009 | **R.1** (FASE RETIRADA, +30 días) |
| 2026-06-18 | Mejora del CIF de contraparte + identidad propia conocida (requisito de Julio sobre la v1) | §11.8 + §3.6 (10-13) + §3.4 + S2.3/S2.4/S2.8 + ADR-0011 | S2.8 (implementación); ADR-0011 (cierre de fuentes) |
| 2026-06-30 | Azure **deprecó `gpt-4.1` y `gpt-4o`** (fin de vida ~mar-2026; al intentar desplegar: *"deprecating state, cannot be used for new deployments"*). Verificado en web (Microsoft Learn, model retirements). Se despliega **`gpt-5.1`** (Sweden Central, Data Zone Standard) como candidato GPT del bench. | §11.7 + §11.10 | ADR-0007 (lo confirma el bench) |

### 11.4 Hallazgos de seguridad abiertos (informativos)
| Hallazgo | Máquina | Acción |
|---|---|---|
| Puerto `2222` expone el SSH del contenedor `setex-prod-backend` a Internet | VPS A | Revisar en **R.1** (tocar la v1 requiere OK de Julio) |
| Staging de la v1 corre en la máquina de producción | VPS A | Se resuelve al retirar la v1 (**R.1**) |

### 11.5 Issues de seguimiento (GitHub)
| # | Título | Motivo |
|---|---|---|
| #2 | Migrar DNS a Cloudflare antes del go-live | Pendiente derivado de ADR-0008 |

### 11.7 Decisión de Fase 1 — arquitectura y candidatos OCR (2026-06-15)
> Tras investigación comparativa (3 análisis IA + verificación web) y revisión con Julio. La arquitectura
> híbrida del plan (§4) queda confirmada como estándar de mercado. La elección final del ganador se hace por
> **bench con facturas reales** (tarea 1.2) → ADR-0007. Requisitos nuevos de Julio incorporados: (a) muchas
> plantillas distintas → motores generalistas, sin entrenar plantillas; (b) las facturas pasan por el servidor
> de Julio → se evalúa motor self-hosted; (c) "verificación exacta tipo DNI" → ADR-0010.

> **Revisión 2026-06-16**: actualizado el lineup con los modelos líderes a junio 2026 (ranking OCR Arena: #1 Gemini 3 Flash, #2 Gemini 3 Pro, #3 Claude Opus 4.6, #4 GPT-5.2). Cuentas necesarias: 3 (Azure, Google Cloud —cubre Gemini **y** Claude vía Vertex—, Mistral). Qwen3-VL y PaddleOCR self-hosted.

- **Capa LECTURA (bench)**: **Mistral OCR 4 (`mistral-ocr-4-0`) — CABEZA DE SERIE** (lanzado 2026-06-23; markdown + bloques + bounding boxes + confidencias, 170 idiomas, 4 $/1.000 págs; motor **ya implementado** como arranque de la tarea 1.2, ver `docs/specs/1.2-mistral-ocr4-engine.md` y `docs/ocr/OCR_MISTRAL_4_SETUP.md`) · Azure DocIntel `prebuilt-invoice` v4 (cloud UE, confianza + bounding boxes) · **PaddleOCR-VL self-hosted** (en el servidor, datos no salen, Apache 2.0, ~8,5 GB VRAM o CPU para el POC) · **Qwen3-VL** (mejor VLM OCR open source, JSON de facturas, self-hostable). El ganador formal lo decide el bench (ADR-0007), no la posición de cabeza de serie.
- **Capa 2º LECTOR / semántica (bench)**: **Gemini 3 Flash + Gemini 3 Pro** vía Vertex AI **región UE europe-west4** (retención cero; Flash es nº1 de OCR Arena, barato/rápido = por defecto, Pro para difíciles) · **Claude** vía Vertex UE (misma cuenta Google; fuerte en JSON estricto y baja alucinación; en Vertex `europe-west4` ya hay **Opus 4.8/4.7, Sonnet 4.6, Fable 5** — el pick exacto del bench, p. ej. Sonnet 4.6 por defecto / Opus 4.8 para difíciles, se fija en 1.2) · familia GPT en Azure: **`gpt-5.1`** (Sweden Central, Data Zone Standard; sustituye a `gpt-4.1`/`gpt-4o`, **deprecados por Azure** 2026-06-30, ver §11.3). *(El candidato de lectura de Mistral pasó de OCR 3 a **OCR 4**, ver "Capa LECTURA" arriba.)*
- **Capa VERIFICACIÓN EXACTA "tipo DNI" (ADR-0010, determinista, en TODOS los motores)**: control CIF/NIF/NIE (módulo-23), IBAN (módulo-97), consulta online VIES/AEAT (confirma que el CIF existe y pertenece a la empresa), cuadre aritmético de tramos/total, fecha plausible. Los campos numéricos clave no dependen de la lectura de la IA: se verifican matemáticamente.
- **Enrutado por confianza**: alta→automático · media→segunda lectura · baja/descuadre→revisión humana.
- **Residencia UE confirmada** para todos los candidatos (Azure UE, Vertex europe-west4, Mistral UE, PaddleOCR/Qwen en el propio servidor).
- **Regiones Azure (estado 2026-06-16)**: Document Intelligence en **West Europe** (`autoken-docintel-we`); Azure OpenAI en **Sweden Central** (`autoken-openai-sweden`) porque West Europe daba cuota 0 y gpt-5.1 solo se ofrecía "Global" (rompe RGPD). Tipo de despliegue obligatorio: **Data Zone Standard** o **Standard regional**; NUNCA **Global**. Tener 2 regiones UE no afecta a la residencia. **Resuelto (2026-06-30)**: `gpt-5.1` **desplegado** en Sweden Central (Data Zone Standard). `gpt-4.1`/`gpt-4o` quedaron deprecados por Azure (ver §11.3); el candidato GPT del bench es `gpt-5.1`.

### 11.6 Estado de tareas (Fase 0)
| Tarea | Estado | PR |
|---|---|---|
| 0.1 Repo GitHub | ✅ | #1 |
| 0.2 DNS | ✅ | #3, #4 |
| 0.3 Hardening VPS | ✅ | #5 |
| 0.4 Esqueleto backend | ✅ | #8 |
| 0.5 Esqueleto frontend | ✅ | #10 |
| 0.6 CI | ✅ | #11 |
| 0.7 ADRs 0001-0006 | ✅ | (esta PR) |
| **FASE 0** | ✅ completada | tag `fase-0-done` |

### 11.8 Decisión — CIF de la contraparte e identidad propia conocida (2026-06-18)

> **Origen**: trabajando con la v1, Julio detecta que el OCR falla sobre todo con **CIFs**, y que dos de esos
> CIFs/nombres (los de la **propia empresa** del usuario) **no hace falta leerlos**: ya están tomados en el
> **registro** (la empresa puso su nombre y CIF al darse de alta). Esta sección fija cómo se trabaja, tras
> **investigación de mercado** (cómo lo resuelven los sistemas de facturación con IA y qué fuentes externas
> existen para España, gratuitas o baratas). Se acepta como **ADR-0011** al cerrar las fuentes con datos reales.

#### 11.8.1 Principio
1. **La identidad propia no se lee, se conoce.** Nombre y CIF de la empresa del usuario se **inyectan** desde
   `companies` (registro). El OCR de "su lado" solo (a) confirma que la foto es de SU factura (anti-foto-
   equivocada) y (b) detecta incoherencia con el selector Recibida/Emitida.
2. **El esfuerzo del OCR se concentra** en **fecha**, **importes** (total + tramos) y, sobre todo, el **CIF de
   la CONTRAPARTE** (proveedor si recibida, cliente si emitida) — el campo más frágil y más crítico.
3. **El CIF de la contraparte se verifica en 4 niveles** (barato/rápido → caro/autoritativo):
   - **L1 · Estructura** (mód-23, IBAN mód-97): YA implementado en `ocr/verification.py`. CIF estructuralmente inválido → bloquea.
   - **L2 · Supplier master del tenant** (`counterparties`): si el CIF ya se confirmó antes, se reutiliza su razón social (gratis, mejora con el uso). Es la práctica de Rossum/Veryfi/SAP AP (*vendor master matching*).
   - **L3 · Resolución externa CIF→nombre + existencia** y comparación con el nombre leído por la IA.
   - **L4 · Caché** de resoluciones (`cif_lookups`, con TTL) para no repetir llamadas ni gastar cuota.
4. **Resultado en la UI**: CIF inválido/inexistente → **bloquea** "Confirmar y guardar"; CIF existe pero el
   nombre **no coincide** → **aviso mostrando la razón social oficial**; coincide → verde.

#### 11.8.2 Fuentes externas investigadas (España)
| Fuente | Qué aporta | Coste | Cobertura / límite | Rol propuesto |
|---|---|---|---|---|
| **Supplier master propio** + `ocr_corrections` | CIF↔nombre ya confirmados por humanos | Gratis | Crece con el uso | **Primera línea** (máximo ROI) |
| **AEAT — "Comprobación de NIF de terceros a efectos censales"** (modelos 030/036; web service SOAP/REST) | Confirma pareja **NIF+nombre**: IDENTIFICADO / NO IDENTIFICADO / SIMILAR; cubre entidades y personas físicas | Gratis (requiere **certificado electrónico**) | Censo AEAT completo | **Verificador autoritativo** del par CIF+nombre |
| **VIES** (Comisión Europea, SOAP `checkVatApprox`) | Valida NIF-IVA + devuelve `traderName` | Gratis | ⚠️ Solo operadores dados de alta en el **ROI** (intracomunitarios). Muchos proveedores nacionales NO están → "inválido" pese a CIF correcto | Contrapartes **intra-UE**; NO única fuente nacional |
| **BORME abierto — LibreBOR / OpenMercantil** | CIF→razón social (Registro Mercantil) | Gratis / freemium | Sociedades inscritas; ⚠️ **autónomos NO** | Enriquecimiento CIF→nombre |
| **Comercial — eInforma / Axesor / Informa D&B** | CIF→razón social + datos ricos, SLA | De pago (test gratis) | Muy amplia (incl. autónomos) | Fallback premium opcional |

#### 11.8.3 Estrategia recomendada (orden de implementación en S2.8)
1. **Ahora / gratis / máximo impacto**: *supplier master* por tenant (`counterparties`) + reutilización de CIFs confirmados.
2. **MVP / gratis (CONFIRMADO — Julio tiene certificado, 2026-06-18)**: **AEAT censal** como verificador autoritativo del par CIF+nombre; **VIES** para contrapartes intracomunitarias.
3. **Enriquecimiento / gratis**: **LibreBOR / OpenMercantil** para mostrar la razón social oficial cuando AEAT no devuelva nombre.
4. **De pago, SOLO si hace falta y de coste bajo (decisión de Julio, 2026-06-18)**: **eInforma / Axesor** únicamente para casos que las fuentes gratuitas no cubran (p. ej. autónomos no inscritos); comparar precios antes de contratar.
- Adaptadores con **interfaz común** y *feature flags* por tenant; todo lo externo va con **caché** (`cif_lookups`) y **timeout** (si la fuente no responde a tiempo → "Revisar manual", nunca bloquea por caída de un tercero).

#### 11.8.4 Pantalla de revisión (concreción de la regla 12)
- **Siempre visibles** (sin plegar): **importe total**, **CIF de contraparte** (con su veredicto) y **fecha**.
- **Plegado** en desplegable comprimido: nº factura, nombres, tramos de IVA, IRPF, datos propios, etc.
- **"Confirmar y guardar" deshabilitado** si: CIF de contraparte inválido o inexistente; o CIF propio leído ≠ CIF conocido del usuario; o descuadre aritmético grave (configurable).
- **Aviso en rojo, grande y legible, DEBAJO del botón**: *"Revisa bien los datos antes de confirmar: su veracidad es responsabilidad de quien los confirma."* Complementa el checkbox de la regla 8 y queda en `audit_log`.

#### 11.8.5 Cómo encaja con lo que ya hay (no rompe nada)
- Reutiliza `ocr/verification.py` (L1) tal cual; añade L2-L4 sin tocarlo.
- `companies` ya tiene `cif` y `name`: la inyección de identidad propia es inmediata.
- `ocr_corrections` (mejora continua) y `audit_log` ya previstos: el supplier master se nutre de las confirmaciones.
- Es **aditivo**: nuevas tablas (`counterparties`, `cif_lookups`), nuevos campos en `invoices`, nueva tarea S2.8 y refuerzos de CA en S2.3/S2.4. No altera fases cerradas ni la Fase 1 en curso (solo añade una métrica a 1.2).
- **Fuentes de la investigación**: ver listado al final de `AUDITORIA_PROYECTO.md` (VIES, AEAT censal/ROI, LibreBOR, OpenMercantil, eInforma, Axesor, Veryfi, Rossum/SAP AP).

### 11.9 Backlog de auditoría de código (`Auditoria_Autoken_Javi_22-06-2026.md`)
> Los comportamientos a implementar salen de hallazgos reales de la auditoría, no inventados. Cada BP se
> trabaja con el flujo SDD+TDD (spec en `docs/specs/` → tests de comportamiento → implementación → auditoría).

| Hallazgo | Estado | Dónde queda |
|---|---|---|
| BP-1 — `check_tax_line` muerto; cuadre de totales laxo | ✅ cerrado (PR #26) | `docs/specs/BP-1-cuadre-aritmetico-por-tramo.md` |
| BP-2 — clasificación de control del CIF (N/W/R) "demasiado laxa" | ✅ cerrado **como falso positivo** (PR #28) | `docs/specs/BP-2-clasificacion-control-cif.md` |
| BP-3 — service-locator en `health.py` (DIP) | ✅ cerrado (PR #29) | `docs/specs/BP-3-health-inyeccion-settings.md` |
| BP-4 — validadores no defienden contra `None` | ✅ cerrado (PR #30) | `docs/specs/BP-4-validadores-defienden-none.md` |
| BP-5 — `log_level` traga valores inválidos en silencio | ✅ cerrado (PR #31) | `docs/specs/BP-5-log-level-fail-loud.md` |
| BP-6 — `CheckResult` no preparado para niveles L2/L3/L4 | pendiente | — |

**BP-2 (decisión, 2026-06-29):** verificado el algoritmo **contra fuente** (Orden EHA/451/2008, manual AEAT
modelo 036, Wikipedia ES e implementación de referencia `python-stdnum`). Las fuentes son **contradictorias**
sobre si las claves `N`/`W`/`R` exigen control alfabético; `python-stdnum` lo resuelve aceptando ambos
("conflicting information… we support either"). Como L1 es la verificación estructural y **un falso positivo
bloquea "Confirmar y guardar"** (§3.6 regla 12, ADR-0011), endurecer N/W/R a "solo letra" introduciría
falsos rechazos de CIFs válidos. Se **mantiene** N/W/R como "número o letra"; se conserva la estrictez de
P/Q/S (letra) y A/B/E/H (número). Limpieza asociada: se elimina la clave `K` de `_CIF_LETTER_ONLY` (era
código muerto inalcanzable; `K` no es clave de CIF). Sin cambio de comportamiento observable salvo la
limpieza. Detalle y fuentes: `docs/specs/BP-2-clasificacion-control-cif.md`.

**BP-3 (2026-06-29):** el handler `health()` resolvía `get_settings()` dentro de la función (service locator),
rompiendo DIP e impidiendo sustituir la configuración en test con `app.dependency_overrides`. Se inyecta vía
`Depends(get_settings)`. Refactor de testabilidad: el contrato HTTP del healthcheck no cambia. Detalle:
`docs/specs/BP-3-health-inyeccion-settings.md`.

**BP-4 (2026-06-30):** los validadores de identificadores (`validate_nif/nie/cif/tax_id/iban`) llamaban a
`_normalize(value)` con `value.strip()`, así que un campo no leído por el OCR (`None`, que es justo lo que
produce la regla anti-alucinación) lanzaba `AttributeError` en vez de devolver un veredicto. Se defiende en
el punto único de normalización: `_normalize(None)` → `""` → veredicto "no válido" tranquilo. Las firmas
públicas pasan a aceptar `str | None`. **Decisión de Julio (Opción A):** se cubre `None` y vacío; defender
contra otros tipos (Opción B) se evaluará al final con datos reales. Detalle:
`docs/specs/BP-4-validadores-defienden-none.md`.

**BP-5 (2026-06-30):** `configure_logging` resolvía el nivel con `getattr(logging, nivel.upper(), logging.INFO)`,
así que un `log_level` mal escrito (typo) caía a INFO **en silencio**, y `log_level` era un `str` libre en
`Settings` (ni se detectaba al arrancar). Ahora `log_level` es un `LogLevel(StrEnum)` (conjunto cerrado de
los cinco niveles estándar) con un `field_validator` que solo unifica la caja (`INFO`/`info`): un nivel
inexistente lanza `ValidationError` al construir `Settings` (fail-loud al arrancar). `configure_logging` deja
de usar valor de reserva silencioso. Detalle: `docs/specs/BP-5-log-level-fail-loud.md`.

### 11.10 Entregables y credenciales de Fase 1 — LISTOS (2026-06-30)
> Estado final de lo que Julio tenía que aportar para arrancar el bench OCR (tarea 1.2). Registrado aquí para
> no volver a olvidar qué quedó montado y dónde. Las **tres patas de IA** y el **dataset** están listas.

**Dataset (bench 1.2):** 20 facturas reales en `entregas/facturas/` (14 JPEG + 4 PNG + 2 PDF). El ground truth
se anota en `docs/ocr-eval/` durante 1.1/1.2.

**Credenciales y cuentas (valores reales SOLO en `.env`/`secrets/` del VPS, nunca en el repo):**

| Motor / servicio | Recurso | Región | Variables en `.env` | Estado |
|---|---|---|---|---|
| Azure Document Intelligence | `autoken-docintel-we` | West Europe | `AZURE_DOCINTEL_ENDPOINT`, `AZURE_DOCINTEL_KEY` | ✅ en uso |
| Azure OpenAI (2º lector GPT) | `autoken-openai-sweden`, despliegue `gpt-5.1` (Data Zone Standard) | Sweden Central | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`, `AZURE_OPENAI_DEPLOYMENT=gpt-5.1` | ✅ desplegado |
| Mistral (OCR) | La Plateforme | UE | `MISTRAL_API_KEY` | ✅ key puesta |
| Google Vertex (Gemini + Claude) | proyecto `autoken-ocr`, SA `vertex-bench` (rol *Vertex AI User*) | `europe-west4` | `GOOGLE_CLOUD_PROJECT=autoken-ocr`, `GOOGLE_CLOUD_LOCATION=europe-west4`, `GOOGLE_APPLICATION_CREDENTIALS=secrets/vertex-sa.json` | ✅ habilitado + facturación vinculada |

**Notas que conviene no olvidar:**
- `AZURE_OPENAI_API_VERSION`: la fija el código del bench según el modelo (gpt-5.1 requiere una versión de API
  reciente); no es un secreto ni la pega Julio a mano.
- **Azure renombró nada; Google sí**: "Vertex AI" aparece en consola como **"Agent Platform" / "Gemini
  Enterprise Agent Platform"**; el identificador técnico sigue siendo `aiplatform.googleapis.com`. Los modelos
  de Claude en Vertex **ya no piden aceptar términos** (flujo cambiado respecto a la guía antigua).
- **`gpt-5.1` sustituye a `gpt-4.1`/`gpt-4o`** (deprecados por Azure, ver §11.3). Modelos de Claude disponibles
  en Vertex `europe-west4`: Opus 4.8/4.7, Sonnet 4.6, Fable 5.
- **Self-hosted** (PaddleOCR-VL, Qwen3-VL): los monta Claude Code; no requieren credenciales de Julio.
- **Pendiente de Julio (no bloquea 1.2):** prompt correcto para integrar el **nuevo OCR de Mistral** como
  candidato del bench; SMTP de `soporte@autoken.es`; Excel de las 51 empresas.

### 11.11 Reconciliación de estado + nuevas decisiones (Julio, 2026-07-22)

> **Hallazgo de gobernanza**: este documento y `CLAUDE.md` llevaban desde 2026-07-02 sin actualizarse (§11
> incumplido) pese a que `develop` ya tenía Sprint 1 y Sprint 2 completos hasta **S2.7** (b420e45). Se
> reconcilia aquí y se actualiza el "Estado actual" de `CLAUDE.md`.
>
> **Actualización (misma sesión, tras el merge de esta rama)**: dos sesiones de Julio trabajaron en paralelo
> el 2026-07-22; la otra cerró y mergeó S3.1 (panel de facturas, PR #77) y `docs/guia-en-cristiano` (regla
> 13-bis, `docs/GUIA_EN_CRISTIANO.md`) mientras esta rama esperaba revisión. Se actualiza aquí el estado para
> no reintroducir la misma desactualización que motivó este hallazgo.

**Estado real verificado (git log, 2026-07-22):** Sprint 1 (tenancy/identity/companies) completo. Sprint 2
(intake+OCR) completo salvo **S2.2** (captura guiada PWA) — hoy no existe ningún componente de cámara en el
frontend, solo el placeholder `onRetry` en `ConfirmationScreen`. **Sprint 3 (panel de asesoría) arrancado**:
S3.1 (panel de facturas) cerrado y mergeado (PR #77); quedan S3.2-S3.5. Sprint 4 (panel de plataforma) **no
iniciado** — `platform_admin/` solo tiene el healthcheck.

**Nuevas tareas decididas hoy (petición de Julio, alcance ampliado sobre lo ya planificado):**

| Tarea | Alcance | Decisión de Julio (2026-07-22) |
|---|---|---|
| **S2.9** Preprocesado de imagen (contraste/brillo/saturación) | `ocr/preprocess/enhance.py` (Pillow `ImageEnhance`), parámetros tuneados empíricamente contra el bench de 20 facturas (ground truth ya existente) | — |
| **S2.10** Comparativa original vs. realzada | Tabla nueva `ocr_comparison_runs` (aislada de `ocr_extractions`, no rompe el UNIQUE por fichero ya en producción) | **Activo automáticamente para TODAS las facturas** (nuevas y ya existentes, backfill retroactivo). Julio quiere un **interruptor en un panel admin-tech** (solo él) para apagarlo cuando deje de necesitarlo — es un experimento de unos días, no permanente, por coste. |
| **S4.8** Panel ranking multi-modelo | Expone `ocr/eval/*` + motores vía API; solo visible en panel admin-tech | **Activo automáticamente para TODAS las facturas** (nuevas y ya existentes, backfill retroactivo), con el **mismo interruptor admin-tech** para apagarlo. |
| Motor **Kimi K3** (Moonshot AI) | Investigado (2,8T parámetros, visión nativa, real, lanzado jul-2026) | **Aparcado, no se integra.** Sus servidores están en Singapur (política de privacidad oficial: datos usados para "optimizar modelos", sin DPA/SCC explícito) — **incumple la decisión ya cerrada de "residencia UE confirmada para todos los candidatos" (§11.7)**. No se reconsidera salvo DPA formal o autoalojamiento (inviable a corto plazo: 2,8T parámetros). |
| Candidatos alternativos investigados | **dots.ocr** (rednote-hilab, 3B/1.7B backbone, MIT+addendum, **autoalojable → sin transferencia de datos a terceros, resuelve RGPD de raíz**, fuerte en extracción estructurada de facturas/tablas por benchmark OmniDocBench); Qwen2.5-VL 72B / InternVL3 76B (autoalojables, top en DocVQA); GLM-OCR (mencionado en rankings recientes, pendiente de investigar residencia/API) | Se añaden como candidatos futuros del bench (`ocr/eval`), ninguno integrado aún — próxima tarea de bench cuando Julio lo priorice. |
| Formato IVA sin decimal superfluo | `frontend/src/features/confirmation/percentage.ts` (`formatIvaPercentage`), aplicado solo a `iva_pct` en `taxLineToForm`; `base`/`cuota` sin cambios | Implementado, testeado y mergeado (PR #78). |

**Diseño pendiente de construir (próxima tarea, bloqueante de S2.9/S2.10/S4.8):** mecanismo de interruptor
global (`feature_flags` o `platform_settings`) + rol/permiso **admin-tech** (solo Julio) para activar/desactivar
bloque 1 (comparativa imagen) y bloque 3 (multi-modelo) sin tocar código ni desplegar. Dado que Julio pide que
esto corra **automático sobre todas las facturas incluidas las ya existentes**, el job de backfill se ejecutará
**limitado (throttled)**, no todas las facturas de golpe, para no disparar coste ni límites de tasa de los
proveedores en un instante.

**Advertencia de coste (relevante para el interruptor)**: con el interruptor en ON, cada factura nueva dispara
2 llamadas OCR extra (comparativa) + N llamadas OCR extra (una por motor del panel multi-modelo, hoy N≈5-6:
Azure DocIntel, Azure OpenAI gpt-5.1, Gemini 3 Flash/Pro, Claude Vertex, Mistral OCR4). El backfill sobre las
facturas ya existentes multiplica esto por el volumen histórico. Julio es consciente y lo quiere así por unos
días — el interruptor existe precisamente para no dejarlo así de forma indefinida.

### 11.12 S6.7 — Benchmark real motor × variante (desplegado y ejecutado en Setex, 2026-08-12)

- **Construido:** benchmark sobre facturas confirmadas, separado del pipeline productivo (ADR-0016):
  3 variantes (`original`, `enhanced`, `clahe`) × 6 motores, 18 combinaciones por factura. Puntúa
  contra `invoices` ya confirmadas, campo a campo, reutilizando S6.6 y tolerancia del 2% solo dentro
  de importes de tramos IVA. Los seis motores de una variante corren en paralelo; las variantes y
  facturas, en secuencia. Una caída se persiste como fallo aislado sin abortar las demás.
- **Panel admin-tech:** agregado por grupo de campo y detalle por combinación, únicamente desde los
  resultados persistidos (nunca llama a IA al consultar). Lote retroactivo limitado a 30, progreso
  persistido en Postgres, `pg_advisory_lock` real y endpoints HTTP que permiten engancharse al lote
  ya existente tras doble clic, otra pestaña o recarga.
- **Seguridad, C24 cerrado:** migración `0033_encrypt_ocr_experiment_pii` cifra CIF/nombre de
  contraparte de `ocr_comparison_runs` y `ocr_ranking_entries`, los retira de sus JSONB en la misma
  actualización y actualiza las escrituras nuevas. El Laboratorio descifra solo bajo la
  `tenant_session` del tenant elegido; el Laboratorio consume solo sus resultados reales por campo y
  el endpoint transversal de ejemplos conserva su redacción defensiva y nunca devuelve esos campos.
- **Correcciones de auditoría antes de publicar:** el benchmark se encola solo tras el commit de la
  confirmación (antes el worker podía no ver todavía la factura); `run_ocr_ranking` legado deja de
  ejecutarse automáticamente, evitando coste duplicado; motores sin credenciales producen sus 3
  filas de error seguras (18 combinaciones siempre, sin reintentos caros eternos); la rotación de
  clave cubre las 6 columnas C24; y ningún error de extractor/migración vuelca el mensaje no
  confiable o parámetros de cifrado a logs/BD. El lote retroactivo se endureció con 0034: una función
  SQL atómica crea un único `running` y su snapshot de candidatos, el job se encola post-commit y
  procesa solo ese snapshot; el snapshot lleva RLS `FORCE` fail-closed aunque solo lo lean funciones
  `SECURITY DEFINER` de plataforma. El Laboratorio consulta exclusivamente benchmark real por campo,
  nunca el ranking histórico de autoconsistencia.
- **Verificación:** 40 tests focalizados verdes contra PostgreSQL y Redis reales, incluido un test
  que crea una BD con el esquema 0032, siembra el histórico en claro y aplica 0033. `alembic check`
  verde desde una base migrada a `head`. Frontend: 304 tests, `tsc` y build verdes. El lint de
  frontend solo mantiene un warning preexistente de Fast Refresh en `SessionProvider.tsx`.
- **Despliegue y lote real autorizados por Julio (12/08/2026):** PR #152 fusionada a `develop` con
  CI completa verde. API/worker/frontend reconstruidos y migraciones 0029-0035 aplicadas con
  API+worker detenidos durante el cifrado C24. El lote `d6a9f187-527b-4c35-be93-64f83503c741` tomó
  un snapshot de las 29 facturas confirmadas de Setex y terminó `done` (29/29, 0 documentos
  fallidos) en 27 minutos. Persistió las 522 combinaciones esperadas: 435 lecturas reales correctas
  de disponibilidad (5 motores × 3 variantes × 29) y 87 `engine_failed` de Claude Vertex (las tres
  variantes de las 29 facturas), sin inventar ni sustituir esas lecturas por otra IA. La cuota de
  Claude sigue siendo el bloqueo externo conocido. Comprobación posterior: las 522 filas existen;
  ningún `reading` JSONB contiene claves de CIF/nombre de contraparte y los valores leídos están en
  las columnas cifradas correspondientes. El panel admin-tech ya muestra el resultado en
  `/plataforma/ranking-ocr` y el Laboratorio lo muestra por factura.
- **Resultado real inicial, no extrapolable aún fuera de estas 29 facturas:** Gemini Flash
  `enhanced` obtuvo 91,62% global (175/191), el mejor agregado de las 18 combinaciones; por campo,
  CIF/NIF 89,66% (Flash `original`/`enhanced`, empate), fecha 100% (Azure en las tres variantes y
  Flash `enhanced`, empate), importes 98,84% (Flash/Pro/gpt-5.1 `enhanced`, empate), nombre 58,62%
  (Flash `original`/`enhanced`, empate) y tramos IVA 100% (Flash/Pro en las tres variantes,
  empate). Número de factura queda sin ratio porque ninguna de las 29 verdades confirmadas tenía ese
  campo. Mistral devolvió 87 respuestas de disponibilidad pero 0 aciertos estructurados, como prevé
  su API OCR sin extracción de campos.
- **Reauditoría bloqueante corregida (12/08/2026, sin desplegar ni lanzar coste real):** el fan-out
  de `jobs/ocr.py` deja de ejecutar `run_ocr_ranking` (código S4.8 conservado, pero fuera del camino
  vivo); `build_named_ranking_extractors` conserva los seis motores aunque falte configuración con
  un extractor local indisponible, que persiste `engine_failed` sin llamada externa; el benchmark no
  persiste ni registra `str(exc)` de adaptadores no confiables. `hide_parameters=True` se aplica
  también al engine de Alembic. El inventario de `jobs/key_rotation.py` añade las cuatro columnas de
  `ocr_comparison_runs` y las dos de `ocr_ranking_entries`, verificadas en Postgres real.
- **Lote S6.7 reforzado:** migración `0034_benchmark_batch_snapshot` crea un snapshot de candidatos
  y funciones `SECURITY DEFINER` de mínimo privilegio. `start_benchmark_batch` toma un advisory
  transaction lock, detecta/retorna el lote `running` y crea snapshot+total atómicamente, cerrando
  la carrera `get_running`+`insert`; el worker procesa exclusivamente ese snapshot. El encolado se
  difiere a `after_commit`; si falla la infraestructura de cola se marca el lote `failed`, igual que
  los fallos de conexión/candado/orquestación del worker. OpenAPI declara el contrato 409. Pruebas
  focalizadas: 68 verdes contra Postgres/Redis reales, `ruff` y `mypy` verdes; queda el warning
  conocido deprecado de `arq`/redis durante los tests.

### 11.13 S6.8 + S6.9 — Laboratorio completo y captura de cámara fiable (implementado localmente, 2026-08-13)

- **S6.8 Laboratorio:** el detalle de una factura deja de ser una barra lateral superpuesta. Desde el
  resumen se abre una vista completa que conserva el tenant elegido al volver; permite alternar foto,
  Lecturas 1/2/3 y comparativa IA sin mezclar tablas. El resumen consume exclusivamente el endpoint
  agregado ya existente de S6.7: tarjetas de ganadores por grupo de campo, filtro por campo y cuadrícula
  motor × variante. Los grupos sin verdad confirmada muestran "sin datos comparables" y los fallos de
  proveedor se mantienen explícitos, nunca convertidos en 0% ni sustituidos. No hay endpoints, OCR,
  persistencia ni exposición transversal nueva de PII. El detalle conserva el aislamiento existente de
  `tenant_session` y carga la foto solo bajo demanda a través del endpoint S6.2 ya autorizado.
- **S6.9 Captura:** la cámara trasera pasa a ser preferencia, no requisito: si no existe lente trasera
  se prueba una cámara de vídeo compatible; si el permiso se deniega, no se abre una segunda solicitud
  automática. "Tomar foto" queda deshabilitado como "Preparando cámara..." hasta que el vídeo entrega
  dimensiones reales, evitando procesar frames vacíos. Cuando no hay vista previa se mantiene el selector
  de archivo y se ofrece "Reintentar cámara" cuando el navegador lo soporta; el reintento libera el stream
  anterior antes de solicitar otro y se ignora mientras una solicitud ya está en curso.
- **Verificación local:** 37 pruebas focalizadas (Laboratorio y cámara), 314 pruebas completas de frontend,
  `tsc` y build de producción en verde. El lint conserva únicamente el warning preexistente de Fast Refresh
  en `SessionProvider.tsx`. El build conserva el aviso conocido por el chunk perezoso de OpenCV. Falta la
  verificación manual obligatoria en Android y iPhone reales: permiso concedido/denegado, sin lente trasera,
  reintento y segunda apertura tras volver a la app.
- **Auditoría posterior (2026-08-13):** tres revisiones independientes encontraron dos huecos reales de
  recuperación de S6.9 y uno de legibilidad móvil de S6.8, todos corregidos antes de integrar. Una petición
  `getUserMedia` que no responde ya caduca a los 10 segundos y permite reintentar; un stream concedido cuyo
  vídeo nunca entrega dimensiones muestra también ese reintento, sin ocultar el selector de archivo. Si la
  solicitud caducada resuelve tarde, sus pistas se detienen en vez de reactivar una cámara obsoleta. La matriz
  motor × variante del detalle de factura ahora tiene scroll horizontal en móvil. Nuevas regresiones cubren
  los tres caminos; 316 pruebas frontend, `tsc` y build en verde. La prueba manual Android/iPhone sigue siendo
  el único bloqueo de hardware pendiente.

### 11.14 Hotfix de subida — autorecuperación de ClamAV (2026-08-13)

- **Incidente real:** una subida real desde la cámara recibió `POST /uploads -> 503`. Diagnóstico en el
  despliegue: MinIO/API sanos; `clamav` estaba `unhealthy` y `clamdcheck.sh` devolvía "Unable to contact
  server". La imagen oficial mantenía vivo el contenedor mediante `tail` aunque el proceso `clamd` hubiera
  muerto, por lo que `restart: unless-stopped` no actuaba solo por marcarse `unhealthy`. El fail-closed de
  intake funcionó correctamente: no se guardó ningún fichero sin análisis antivirus.
- **Corrección:** healthcheck con contador local: tras tres fallos consecutivos termina PID 1 para que Docker
  reinicie el contenedor. Durante la ventana de recuperación, la API sigue devolviendo 503 y no degrada a un
  escaneo opcional. El arranque inicial recibe una gracia de diez minutos para cargar la base de firmas antes
  de activar el contador. Reinicio manual aplicado al incidente y verificado con `clamdcheck.sh` + un escaneo
  real desde el contenedor de API. Runbook actualizado.

### 11.15 S6.10 — Captura manual y confirmación segura de CIF (implementada, 2026-08-13)

- **Captura:** se elimina el disparo automático por análisis de frames. Entrar en `/capturar` no pide permiso
  de cámara: "Abrir cámara" abre una capa visual completa, accesible y separada del panel, con vista previa,
  marco A4 vertical grande, botón manual y selector de archivo. Cerrar, tomar foto, repetir o elegir archivo
  detiene siempre el stream; un resultado o rechazo tardío de `getUserMedia`, OpenCV o decodificación de
  fichero no puede reabrir cámara ni reemplazar una captura más reciente.
- **CIF conocido:** el CIF de la empresa registrado al alta es la referencia cierta de cada fichero (receptor
  en recibida, emisor en emitida); OCR solo debe encontrarlo, nunca inventarlo. Si falta, un `user` puede
  marcar una aceptación explícita con razón social y CIF de su empresa. La confirmación persiste de forma
  inmutable `own_tax_id_missing` y, solo cuando corresponde, `own_tax_id_exception_confirmed`; un
  `tenant_admin` conserva la excepción sin esa casilla. El panel y Excel muestran/filtran "Revisar CIF propio".
  No se marcan facturas históricas de forma retrospectiva: `ocr_extractions` se sobrescribe al reprocesar y no
  es evidencia fiable del instante de confirmación.
- **CIF de contraparte:** `POST /uploads/{file_id}/counterparty-verdict` recalcula el veredicto sobre los
  valores actuales del formulario, con pausa de edición en cliente, descarte de respuestas antiguas, límite
  de 30 comprobaciones/minuto por usuario+tenant y autorización idéntica a review/confirm. `POST confirm`
  vuelve a validar siempre y devuelve su veredicto estructurado si cambió, que la UI aplica en vez de conservar
  un check viejo. El endpoint está añadido al gate anti-cruce y al OpenAPI generado.
- **Auditoría de 3 lentes:** se corrigieron antes de cerrar 5 hallazgos altos (veredicto de servidor ignorado,
  carreras de cámara/capturas, migración mutable de histórico, endpoint fuera del gate de aislamiento y abuso
  de verificaciones externas) y 3 medios (marco no A4, contrato OpenAPI manual y accesibilidad pendiente de
  prueba física). Verificación: 10 pruebas backend focalizadas (incluida la suite de aislamiento) contra
  Postgres/Redis reales; `ruff`/`mypy` verdes; 320 pruebas frontend, `tsc` y build verdes. La suite backend
  completa llega a 85 tests verdes y se detiene únicamente en los 8 tests de backup porque este host no tiene
  `pg_dump`/`pg_restore`; no es regresión de S6.10. Prueba manual Android/iPhone sigue obligatoria.

### 11.16 S6.11 — Captura directa desde cámara completa (implementada, 2026-08-13)

- **Decisión de flujo de Julio:** el panel inicial conserva visibles Recibida/Emitida, "Tomar foto" y "Subir
  archivo". "Tomar foto" abre la cámara en pantalla completa con guía A4 grande; "Capturar foto" apaga la
  cámara, normaliza y sube inmediatamente, sin revisión intermedia ni botón "Usar esta foto". Al aceptar la
  API, muestra "Procesando factura..." y navega a comprobación, que ya espera el OCR de forma segura.
- Un `tenant_admin` debe elegir empresa antes de abrir cámara o selector; un `user` conserva la empresa fija.
  Los resultados asíncronos tardíos no pueden sustituir una captura posterior ni subir tras desmontar. 310
  pruebas frontend, `tsc`, lint sin errores y build verdes; auditoría adversarial sin bloqueantes. Pendiente
  obligatorio: prueba manual Android/iPhone real.

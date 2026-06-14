# PLAN MAESTRO — Autoken Facturas v2 (Setex v2)
**Plataforma SaaS multi-asesoría de digitalización de facturas con OCR/IA**
Versión 1.1 — 11/06/2026 — Documento de ejecución para Claude Code, supervisado por Julio
**v1.1: datos de arranque confirmados (GitHub, dominio, VPS, emails, cuentas IA) — listo para ejecutar**

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

Toda tabla de negocio: índice compuesto que empieza por `tenant_id`.

### 3.5 Ficheros (MinIO)
- Bucket por tenant: `invoices-<tenant_id>`. Original SIEMPRE conservado (imagen/PDF) + versión procesada.
- Antivirus ClamAV + validación de MIME real + límite de tamaño en el upload.
- Hash SHA-256 del fichero → detección de duplicados (regla ya existente en v1, se conserva).

### 3.6 Reglas de negocio confirmadas de la v1 (se conservan todas)
1. Selector Recibida/Emitida ANTES de capturar.
2. El CIF del usuario debe aparecer en la factura (como receptor si es recibida, como emisor si es emitida). Si no aparece → aviso bloqueante. Excepción: admins (tenant y plataforma).
3. Facturas de prueba de admins: flag `is_test`, excluidas de informes, purga con un clic.
4. Aviso de duplicado (hash + heurística nº factura + CIF + fecha + total).
5. Validación aritmética: Σ(base×IVA%) = cuota por tramo, Σ tramos + IVA − IRPF = total. Descuadre → aviso "Revisar".
6. Validación de dígito de control de CIF/NIF (algoritmo oficial, determinista).
7. Confirmación humana obligatoria con todos los campos editables ANTES de guardar.
8. **NUEVO**: checkbox "He revisado que los datos coinciden con la factura — la veracidad de los datos es responsabilidad de quien los confirma" + registro en audit_log (quién, cuándo, snapshot de datos).
9. Panel admin asesoría: filtros (fechas, proveedor/CIF, usuario, estado), tabla completa (tramos IVA, IRPF, totales, estado, imagen "Ver", fecha subida), export Excel, edición de campos (auditada), gestión de empresas (alta/pendiente/activa) y aprobación de usuarios.

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
- **1.2 Bench motores** — CA: script que pasa el dataset por Azure prebuilt-invoice, GPT-4o visión y Mistral OCR 3; tabla de precisión por campo (nº factura, CIFs, nombres, fecha, tramos, total), coste y latencia. Informe en `docs/ocr-eval/resultado-poc.md`.
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
- **S2.3 Worker OCR** — CA: job arq con los motores ganadores del POC en paralelo (asyncio.gather), árbitro por campo, validaciones deterministas, persistencia en `ocr_extractions`. Regla anti-alucinación verificada con test (factura con CIF tapado → campo null, no inventado).
- **S2.4 Pantalla de confirmación** — CA: idéntica a la actual (empresa IA / receptor / fecha / total / tramos IVA editables / IRPF / resumen / Confirmar / Repetir foto) + colores de confianza (amarillo=dudoso, rojo=no leído) + checkbox de responsabilidad + regla "tu CIF debe aparecer en la factura" + descuadres marcados.
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
- [ ] **Azure Document Intelligence**: crear recurso en la cuenta Azure existente, región **West Europe**, tier S0 (PDF paso 4A) → clave a GitHub Secrets + `.env`.
- [ ] **Azure OpenAI** (motor LLM de visión, residencia UE, misma factura Azure): crear recurso + despliegue `gpt-4o` (PDF paso 4B). ChatGPT Pro NO sirve (es suscripción de consumidor, no API).
- [ ] **Mistral La Plateforme**: cuenta + clave API solo para el POC (PDF paso 4C).
- [ ] SMTP de `soporte@autoken.es`: confirmar buzón con Alberto y obtener credenciales SMTP del proveedor de correo (PDF paso 6).
- [ ] Excel de las 51 empresas de Setex → carpeta `entregas/` que indicará Claude Code.
- [ ] Facturas reales para el POC (15-30, descargables de la v1) → misma carpeta (PDF paso 7).
- [ ] Logo Setex: no hace falta entregar nada — se extrae de la v1 (tarea D.2); si Julio tiene el archivo original (PNG/SVG), mejor: entregarlo.

### 9.1 Mapa de secretos (referencias, NUNCA valores)
| Secreto | Dónde vive |
|---|---|
| `AZURE_DOCINTEL_KEY` / `AZURE_DOCINTEL_ENDPOINT` | GitHub Secrets + `.env` del VPS |
| `AZURE_OPENAI_KEY` / `AZURE_OPENAI_ENDPOINT` | GitHub Secrets + `.env` del VPS |
| `MISTRAL_API_KEY` (solo POC) | GitHub Secrets + `.env` del VPS |
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
| ADR-001..006 | Reservados (se redactan en la tarea 0.7) | pendiente |
| ADR-007 | Motores OCR ganadores (tras Fase 1) | pendiente |
| **ADR-0008** | DNS en Hostinger durante el desarrollo (enmienda a ADR-004) | aceptado |
| **ADR-0009** | Hardening mínimo del VPS A; construir todo en VPS B | aceptado |

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

### 11.4 Hallazgos de seguridad abiertos (informativos)
| Hallazgo | Máquina | Acción |
|---|---|---|
| Puerto `2222` expone el SSH del contenedor `setex-prod-backend` a Internet | VPS A | Revisar en **R.1** (tocar la v1 requiere OK de Julio) |
| Staging de la v1 corre en la máquina de producción | VPS A | Se resuelve al retirar la v1 (**R.1**) |

### 11.5 Issues de seguimiento (GitHub)
| # | Título | Motivo |
|---|---|---|
| #2 | Migrar DNS a Cloudflare antes del go-live | Pendiente derivado de ADR-0008 |

### 11.6 Estado de tareas (Fase 0)
| Tarea | Estado | PR |
|---|---|---|
| 0.1 Repo GitHub | ✅ | #1 |
| 0.2 DNS | ✅ | #3, #4 |
| 0.3 Hardening VPS | ✅ | #5 |
| 0.4 Esqueleto backend | ✅ | #8 |
| 0.5 Esqueleto frontend | ⏳ en curso | — |
| 0.6 CI · 0.7 ADRs | pendiente | — |

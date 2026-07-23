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
| `POSTGRES_PASSWORD`, `MINIO_KEYS`, `JWT_SECRET`, claves Fernet por tenant | Generados en el VPS, solo en `.env`/volúmenes cifrados |
| Contraseñas de login Julio/Alberto | En ningún sitio: se crean en el primer login con 2FA |

## Infra (recordatorio crítico de seguridad)
- **VPS A `72.60.186.89`**: ejecuta la **v1 de Setex EN PRODUCCIÓN**. NO SE TOCA salvo el hardening de acceso de la tarea 0.3.
  Cualquier otro comando sobre esa máquina requiere autorización explícita previa de Julio en el chat.
- **VPS B `2.24.8.109`**: aquí se construye la v2 (staging durante el desarrollo, producción en go-live).
- Dominio: `autoken.es` (Cloudflare, `*.autoken.es` → VPS B). Subdominios de primer nivel (ADR-004).

---

## Estado actual (reconciliado 2026-07-22 — ver PLAN MAESTRO §11.11)
- **Fase real (git log)**: Sprint 1 (tenancy/identity/companies) completo. Sprint 2 (intake+OCR) completo
  salvo S2.2. **Sprint 3 (panel de asesoría) COMPLETO**: S3.1 (panel de facturas, PR #77), S3.2 (export
  Excel, PR #80), S3.3 (edición auditada, PR #81), S3.4 (gestión de empresas/usuarios, PR #82) y S3.5
  (facturas de prueba) cerrados y mergeados.
- **Falta de Sprint 2**: **S2.2** (captura guiada PWA, `getUserMedia`+OpenCV.js, ADR-0002) — sin empezar, no
  hay ningún componente de cámara en frontend hoy.
- **Sprint 4 (panel de plataforma)**: no iniciado; `platform_admin/` solo tiene el healthcheck. Es el
  siguiente sprint a abordar.
- **Hallazgo transversal (S3.4, 2026-07-23)**: las pantallas de frontend construidas hasta ahora
  (historial, confirmación, panel de facturas, empresas) viven y se prueban aisladas; falta una tarea de
  integración (app-shell: login real, menú, routing) que las conecte entre sí antes de un demo end-to-end.
- **Guía en cristiano viva**: `docs/GUIA_EN_CRISTIANO.md` (regla 13-bis) ya mergeada; se actualiza al cerrar
  cada tarea.
- **Nuevas tareas decididas por Julio 2026-07-22 (detalle en plan §11.11), aún sin construir**:
  - **S2.9/S2.10**: preprocesado de imagen (contraste/brillo/saturación máx.) + comparativa original-vs-realzada,
    **activo automáticamente en todas las facturas** (nuevas + backfill retroactivo de las existentes), con
    interruptor admin-tech (solo Julio) para apagarlo — experimento de coste acotado en el tiempo.
  - **S4.8**: panel de ranking multi-modelo (Azure DocIntel, gpt-5.1, Gemini 3 Flash/Pro, Claude Vertex,
    Mistral OCR4...), **activo automáticamente en todas las facturas** (nuevas + backfill), mismo interruptor.
  - **Kimi K3 aparcado**: servidores en Singapur, sin DPA/SCC — incumple la decisión ya cerrada de residencia
    UE (§11.7). Candidatos alternativos investigados: **dots.ocr** (autoalojable, resuelve RGPD de raíz),
    Qwen2.5-VL 72B, InternVL3 76B.
  - **Formato IVA sin ".0"/",0" superfluo**: implementado (`percentage.ts`, PR #78).
- **Pendiente de construir**: interruptor global (feature flag) + rol admin-tech, prerrequisito de S2.9/S2.10/S4.8.

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

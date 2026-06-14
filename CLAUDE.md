# CLAUDE.md — Resumen operativo Autoken Facturas v2

> Fuente de verdad: **`PLAN_MAESTRO_AUTOKEN_FACTURAS_V2_v1.1.md`**. Este archivo es un resumen de arranque
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

## Estado actual
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
- **Nota**: el proyecto vive en **`/opt/app-facturas/`** (no en `/opt`). Clave SSH en `~/.ssh/autoken_deploy`.
- **Próxima tarea**: **0.4 Esqueleto backend** (FastAPI en Docker, `/api/v1/health`, structlog,
  pydantic-settings, Alembic). Autónoma.
- Luego: 0.5 frontend → 0.6 CI → 0.7 ADRs → tag `fase-0-done` + demo.

### Pendientes de Julio (sección 9 del plan)
- [x] Autenticación GitHub para Claude Code (hecha vía `gh auth login`).
- [x] **0.2**: 5 registros A en hPanel de Hostinger creados y verificados (tenant demo = `tuti`).
- [x] **0.3**: acceso SSH entregado; VPS B endurecido completo, VPS A mínimo.
- [ ] Azure Document Intelligence (West Europe, S0), Azure OpenAI (gpt-4o), Mistral (POC), SMTP soporte@autoken.es.
- [ ] Excel 51 empresas + 15-30 facturas reales → carpeta `entregas/`.

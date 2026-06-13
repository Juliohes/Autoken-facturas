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
- **Tarea en curso**: **0.2 DNS de `autoken.es`** — DECISIÓN: se gestiona en **Hostinger** durante el
  desarrollo (no Cloudflare), por comodidad de Julio y porque no aporta nada en staging. Documentado en
  **ADR-0008** (enmienda a ADR-004). Caddy hace el HTTPS. Cloudflare se valorará antes del go-live (issue de
  seguimiento). **Acción pendiente de Julio**: añadir 5 registros A (`setex`/`panel`/`joseramon`/
  `setex-staging`/`panel-staging` → `2.24.8.109`) en hPanel → Zona DNS. Luego Claude verifica con `dig` y cierra.
- **Nota**: el proyecto vive en **`/opt/app-facturas/`** (no en `/opt`).
- Luego: 0.3 hardening VPS → 0.4 backend → 0.5 frontend → 0.6 CI → 0.7 ADRs → tag `fase-0-done` + demo.

### Pendientes de Julio (sección 9 del plan)
- [x] Autenticación GitHub para Claude Code (hecha vía `gh auth login`).
- [ ] **0.2**: añadir los 5 registros A en hPanel de Hostinger (DNS en Hostinger, ADR-0008).
- [ ] Azure Document Intelligence (West Europe, S0), Azure OpenAI (gpt-4o), Mistral (POC), SMTP soporte@autoken.es.
- [ ] Acceso SSH a los 2 VPS para la tarea 0.3 (hardening).
- [ ] Excel 51 empresas + 15-30 facturas reales → carpeta `entregas/`.

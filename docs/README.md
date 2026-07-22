# Documentación — Autoken Facturas v2

- [`GUIA_EN_CRISTIANO.md`](./GUIA_EN_CRISTIANO.md) — qué hace la app y cómo está construida por dentro,
  explicado en lenguaje llano para Julio. Se actualiza al cerrar cada tarea (regla 13-bis del `CLAUDE.md`).
- `adr/` — Architecture Decision Records. Plantilla: [`0000-template.md`](./adr/0000-template.md).
  ADRs iniciales (001-006) en la tarea **0.7**; ADR-007 (motores OCR) tras la Fase 1.
- `runbooks/` — Procedimientos operativos: provisioning (0.3), rollback (§2.4), backups/restore (S5.3).
- `ocr-eval/` — Dataset de evaluación OCR con ground-truth anotado (§4, Fase 1).
  **Las imágenes/PDF de facturas reales NO se versionan** (datos sensibles, ver `.gitignore`).

Fuente de verdad: [`../PLAN_MAESTRO_AUTOKEN_FACTURAS_V2_v1.2.md`](../PLAN_MAESTRO_AUTOKEN_FACTURAS_V2_v1.2.md).

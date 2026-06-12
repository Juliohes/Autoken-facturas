<!-- PR a `develop`. Una rama feature por tarea del plan. Conventional Commits. -->

## Tarea del plan
- **ID**: <!-- ej. S1.1 -->
- **Título**: <!-- ej. Modelo tenants + branding + RLS -->

## Qué hace este PR
<!-- Resumen claro para Julio, en español. -->

## Criterio de aceptación (del plan)
<!-- Pega el CA de la tarea y marca cómo se cumple. -->

## Definition of Done (plan §7)
- [ ] Código completo, tipado y lintado (sin `...` ni TODOs silenciosos).
- [ ] Tests: caso feliz + errores + (si toca datos) aislamiento de tenant.
- [ ] CI en verde (lint, tipos, tests, **suite anti-cruce**, gitleaks, audit, build).
- [ ] Migraciones con `downgrade` implementado y testeado (si aplica).
- [ ] Docs/ADR actualizados si cambia comportamiento o arquitectura.
- [ ] Commits con Conventional Commits y referencia al ID de tarea.

## Seguridad
- [ ] Ningún secreto añadido al repo.
- [ ] Si toca datos de tenant: suite anti-cruce ampliada/verde.
- [ ] Si toca OCR: regla anti-alucinación respetada (campo no legible = `null`).

## Notas / decisiones
<!-- Enlaza ADRs nuevos. Riesgos o pendientes (con issue creada). -->

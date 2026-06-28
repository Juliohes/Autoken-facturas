---
name: spec
description: Redactar o revisar una spec Spec-Driven Domain (SDD) antes de implementar una tarea. Usar cuando el usuario quiere arrancar una tarea/feature, clarificar requisitos, o pide "/spec", "escribe la spec", "definamos el comportamiento". Produce docs/specs/<ID>-<slug>.md con criterios Given/When/Then. NO escribe tests ni código de producción.
---

# Skill: Spec-Driven Domain (fase A)

Objetivo: convertir una idea difusa en una **spec de comportamiento** clara y aprobable, que sea la fuente
única para los tests (TDD) y las 3 auditorías. Esto es el equivalente a planificar requisitos ANTES de tocar código.

## Cuándo se usa
Al iniciar cualquier tarea de la fase actual del PLAN MAESTRO. Es el primer gate: Julio aprueba la spec
antes de que se escriba un solo test (regla de oro 1).

## Proceso
1. **Localiza el contexto.** Lee el `CLAUDE.md` del proyecto y el `PLAN_MAESTRO_*` para entender la tarea
   por su ID. Identifica el módulo (`backend/src/<contexto>/`) y los ADR relevantes. NO modifiques el PLAN
   MAESTRO (memoria: documentar solo al cerrar).
2. **Pregunta lo imprescindible.** Si falta información de dominio que cambie el comportamiento (regla de
   negocio, caso límite, qué pasa si la dependencia externa falla), pregunta a Julio. No inventes requisitos.
3. **Redacta la spec** copiando `docs/specs/_template.md` a `docs/specs/<ID>-<slug>.md` y rellenándolo:
   - Lenguaje ubicuo del dominio (términos con significado exacto).
   - Cada comportamiento como un escenario **Given / When / Then** observable, numerado (C1, C2, ...).
     Un escenario = un test futuro. Describe comportamiento del usuario/sistema, no detalles de implementación.
   - Invariantes (anti-alucinación OCR, anti-cruce de tenants, y las propias).
   - Casos límite, errores, y **fuera de alcance** explícito (evita que implementer y auditores inventen).
4. **Cierra con el gate.** Presenta un resumen y pide aprobación explícita a Julio. No avances a `/tdd-behavior`
   hasta que diga que la spec está aprobada. Marca `Estado: aprobada por Julio` en la cabecera al confirmarlo.

## Reglas
- Comportamiento, no implementación: la spec dice QUÉ debe ocurrir, no CÓMO.
- Si un criterio no es comprobable de extremo a extremo, reescríbelo hasta que lo sea.
- Mantén el alcance pequeño: una spec por comportamiento acotado, no una spec gigante por sprint entero.

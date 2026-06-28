---
name: audit
description: Auditar en paralelo lo implementado contra la spec y los tests, lanzando 3 subagentes revisores (SOLID, arquitectura, patrones+seguridad) en contexto fresco, y sintetizar un veredicto con gate. Usar tras el implementer, cuando los tests están en verde y el usuario pide "/audit", "audita esto", "revisa el cambio".
---

# Skill: Auditoría adversarial en 3 lentes (fases D + E)

Objetivo: revisión independiente y adversarial del cambio, en contexto fresco, ANTES del commit/PR. Tres
lentes distintas miran el mismo diff contra la misma spec y tests, y luego se sintetiza un veredicto. Es el
equivalente al "revisor adversarial en contexto fresco" pero especializado en tres dimensiones.

## Precondición
El `implementer` ha dejado los tests de la spec en verde. Identifica:
- La spec: `docs/specs/<ID>-<slug>.md`.
- El diff bajo revisión: `git diff` contra la rama base (normalmente `develop`).
- Los tests de comportamiento de la spec.

## Proceso
1. **Lanza los 3 subagentes EN PARALELO** (una sola respuesta con tres invocaciones de la herramienta Agent):
   - `reviewer-solid`
   - `reviewer-architecture`
   - `reviewer-patterns-security`
   A cada uno pásale en el prompt: la ruta de la spec, el rango de diff (`git diff develop...HEAD` o el diff de
   trabajo), y la ruta de los tests. Instrúyelos a ser adversariales: buscar dónde el código DIVERGE de la spec
   o de los tests, no solo estilo.
2. **Recoge los hallazgos estructurados** de los tres (severidad, fichero:línea, criterio de spec violado,
   justificación, arreglo sugerido).
3. **Sintetiza (fase E):**
   - Deduplica hallazgos que coinciden entre lentes.
   - Clasifica: **BLOQUEANTE** (crítico/alto: viola spec, invariante, seguridad o un test) vs **AVISO** (medio/
     bajo: mejora de calidad). Por defecto: crítico y alto bloquean; medio y bajo son avisos.
   - Verifica de nuevo que la suite pasa (`pytest`) y que no hay regresión del gate de aislamiento de tenants.
4. **Veredicto y gate:**
   - Si hay BLOQUEANTES: devuelve la lista al `implementer` para corregir (o escala a Julio si es ambiguo y
     tiene implicación de producto/dominio). No se hace commit con bloqueantes abiertos.
   - Si solo hay AVISOS: preséntalos a Julio para que decida, y procede al commit atómico + PR (reglas 2/12).
5. **Deja evidencia** en el resumen: qué encontró cada lente, qué se corrigió, qué queda como aviso aceptado.

## Reglas
- Los revisores NO editan código (son read-only); solo el `implementer` corrige. Mantiene separación de roles.
- Un hallazgo sin fichero:línea y sin criterio/justificación no cuenta: pídelo de nuevo.
- No marques "todo correcto" sin haber ejecutado los tests en esta fase.

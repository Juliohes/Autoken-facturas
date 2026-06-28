---
name: tdd-behavior
description: Escribir tests de comportamiento que FALLAN (fase roja del TDD) a partir de una spec aprobada, antes de implementar. Usar cuando hay una spec en docs/specs/ aprobada y el usuario pide "/tdd", "escribe los tests", "fase roja". Un escenario Given/When/Then de la spec = un test. NO escribe código de producción.
---

# Skill: TDD de comportamiento — fase roja (fase B)

Objetivo: traducir cada criterio de aceptación de la spec en un test que **falla por la razón correcta**
(porque el comportamiento aún no existe), nunca por error de import o sintaxis. Sin escribir código de producción.

## Precondición
Debe existir `docs/specs/<ID>-<slug>.md` con `Estado: aprobada por Julio`. Si no, vuelve a `/spec` primero.

## Proceso
1. **Lee la spec entera.** Enumera los criterios C1, C2, ... y las invariantes.
2. **Brainstorming de casos (deseados vs no deseados).** ANTES de escribir un solo test, piensa en términos
   del usuario y el dominio, no de la función:
   - **Casos que SÍ deben ocurrir** (el sistema funciona para el usuario): caminos legítimos, variantes reales
     del negocio, redondeos/tolerancias que NO deben molestar al usuario con falsos rechazos.
   - **Casos que NO deben ocurrir** (de los que protegemos al usuario): el dato malo que se cuela, el error
     silencioso, el falso positivo que bloquea algo legítimo, el mensaje inútil que no dice qué revisar, la
     excepción no controlada en vez de un veredicto.
   - Mapea cada caso a un criterio existente de la spec (C#) o márcalo como **caso nuevo**. Si el brainstorming
     destapa un comportamiento real que la spec no cubre o una decisión de dominio (p. ej. importes negativos /
     facturas rectificativas), **no lo decidas en silencio**: súbelo a Julio (puede volver a `/spec`).
   - Presenta el brainstorming a Julio antes de codificar los tests. Es barato y caza huecos que la spec, escrita
     "desde dentro", no vio.
3. **Un test por comportamiento.** En `backend/tests/`, crea `test_<contexto>_<comportamiento>.py`.
   - Nombra cada test por el comportamiento observable, no por el método interno:
     `test_cif_de_contraparte_mal_formado_bloquea_el_guardado`, no `test_validate_returns_false`.
   - El cuerpo sigue Given/When/Then (arrange/act/assert) tal cual el escenario de la spec.
   - Añade un comentario `# spec: C1` enlazando el test con su criterio para trazabilidad y para las auditorías.
4. **Cubre invariantes y casos límite** (los del brainstorming), no solo el camino feliz: anti-alucinación
   (campo no legible -> null, nunca valor inventado), anti-cruce de tenants, errores de dependencias externas.
5. **Prefiere comportamiento de extremo a extremo** sobre unit triviales: usa el cliente de API / fixtures
   reales cuando el comportamiento sea observable ahí. Un unit aislado solo si el comportamiento es puramente
   de una función de dominio (ej. verificación mód-23).
6. **Ejecuta y confirma ROJO.** `cd backend && pytest tests/test_<...>.py -v`. Verifica que falla por aserción
   o por símbolo de dominio aún no implementado, NO por import roto del propio test. Reporta el resumen rojo.
7. **No implementes.** Termina aquí y pasa el control: el siguiente paso es el subagente `implementer`.

## Reglas
- Si un criterio de la spec no se puede expresar como test, es señal de que la spec es ambigua: vuelve a `/spec`.
- No escribas tests para comportamientos que la spec marca como fuera de alcance.
- No relajes una aserción para que pase: en esta fase los tests DEBEN estar en rojo.

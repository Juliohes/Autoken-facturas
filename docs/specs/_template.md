# Spec: <ID> <Título del comportamiento>

> Spec-Driven Domain. Esta spec es la **fuente única** que alimenta los tests (TDD) y las 3 auditorías.
> Si algo no está aquí, no se implementa. Aprobada por Julio antes de escribir tests.

- **ID / tarea:** <ej. S2.8>
- **Contexto (módulo):** <ej. invoice_intake, ocr, tenancy...>
- **ADR relacionados:** <ej. ADR-0010, ADR-0011 o "ninguno">
- **Estado:** borrador | aprobada por Julio | implementada

## 1. Problema y valor de dominio
<Qué necesita el usuario y por qué importa. En lenguaje de negocio, no técnico.>

## 2. Lenguaje ubicuo
<Términos del dominio con su significado exacto. Ej.: "contraparte" = emisor/receptor distinto del propio
tenant; "CIF inválido" = no pasa estructura mód-23 o no existe en censo.>

## 3. Comportamientos (criterios de aceptación)
> Cada escenario Given/When/Then se convierte en **un** test de comportamiento. Numéralos.

### C1 — <nombre del comportamiento>
- **Given** <estado / contexto previo>
- **When** <acción del usuario o del sistema>
- **Then** <resultado observable esperado>

### C2 — <...>
- **Given** ...
- **When** ...
- **Then** ...

## 4. Invariantes y reglas de negocio
<Cosas que SIEMPRE deben cumplirse, independientemente del escenario.>
- Anti-alucinación: campo no legible = `null` + aviso; nunca un valor inventado llega a la UI.
- Anti-cruce de tenants: ninguna operación cruza la frontera del tenant.
- <otras invariantes propias del comportamiento>

## 5. Casos límite y errores
<Entradas vacías, límites, fallos de dependencias externas, concurrencia, idempotencia...>

## 6. Fuera de alcance (no-objetivos)
<Lo que esta tarea explícitamente NO hace. Evita que el implementer y los auditores se inventen requisitos.>

## 7. Notas de verificación (cómo se prueba de extremo a extremo)
<Cómo comprobar el comportamiento como lo vería el usuario final: endpoint, fixture, datos de ejemplo.>

# Spec: BP-4 Los validadores defienden contra `None` (campo no leído = `null`)

> Spec-Driven Domain. Esta spec es la **fuente única** que alimenta los tests (TDD) y las auditorías.
> Si algo no está aquí, no se implementa. Aprobada por Julio antes de escribir tests.

- **ID / tarea:** BP-4 (hallazgo de `Auditoria_Autoken_Javi_22-06-2026.md`)
- **Contexto (módulo):** ocr (`backend/src/ocr/verification.py`)
- **ADR relacionados:** ADR-0010 (verificación determinista "tipo DNI")
- **Estado:** aprobada por Julio (2026-06-30)

## 1. Problema y valor de dominio
Por la regla anti-alucinación (Regla de Oro 4), un campo que el OCR no consigue leer se entrega como
`null` (`None` en Python), no como un valor inventado. Pero los validadores de identificadores
(`validate_nif/nie/cif/tax_id/iban`) llaman a `_normalize(value)`, que ejecuta `value.strip()`. Si `value`
es `None`, eso lanza `AttributeError` y **rompe la verificación** en vez de devolver un veredicto.

Es una contradicción directa con la regla anti-alucinación: justo el caso que esa regla genera (campo no
leído = `null`) es el que hace estallar la capa que debería tratarlo con normalidad. El valor de BP-4 es que
un campo no leído produzca un veredicto **"no válido"** tranquilo (que la pantalla de revisión muestra),
nunca una excepción.

## 2. Lenguaje ubicuo
- **Campo no leído (`None`/`null`)**: el OCR no pudo extraer el dato. Por la regla anti-alucinación se
  representa como `None`, nunca como un valor inventado.
- **Veredicto**: el `CheckResult(valid, reason)` que devuelve un validador. Un campo no leído es un veredicto
  legítimo de "no válido" (`valid=False`), no un error de programa.

## 3. Comportamientos (criterios de aceptación)

### C1 — Un identificador `None` devuelve "no válido", nunca lanza  *(el bug de BP-4)*
- **Given** `None` como valor para cualquiera de `validate_nif`, `validate_nie`, `validate_cif`,
  `validate_tax_id` o `validate_iban`
- **When** se valida
- **Then** el resultado es `CheckResult(valid=False, ...)` con un `reason` no vacío, y **nunca** se lanza una
  excepción (hoy lanza `AttributeError`)

### C2 — Una cadena vacía o de solo separadores también devuelve "no válido", sin lanzar
- **Given** `""` o `"   "` o `" - . "` (solo espacios/guiones/puntos) para los mismos validadores
- **When** se valida
- **Then** el resultado es `valid=False` con `reason` no vacío, sin excepción

### C3 — Los valores legítimos siguen validando igual (no hay regresión)
- **Given** identificadores válidos e inválidos "de verdad" (texto con contenido) ya cubiertos por los tests
  existentes
- **When** se validan
- **Then** el veredicto es el mismo que antes de BP-4 (la defensa contra `None`/vacío no altera el resto)

## 4. Invariantes y reglas de negocio
- **Anti-alucinación coherente:** un campo no leído (`None`) o vacío es un veredicto "no válido" tranquilo;
  la capa de verificación **nunca** lanza por recibir el `null` que la propia regla anti-alucinación produce.
- **Alcance Opción A (decisión de Julio, 2026-06-30):** se defiende contra `None` y contra cadena vacía /
  solo separadores. **NO** se defiende contra otros tipos equivocados (`int`, `list`, ...): el contrato sigue
  siendo "entra texto (o `None`)". La defensa contra tipos arbitrarios (Opción B) se evaluará al final, si los
  datos reales lo piden.
- **Punto único:** la defensa vive en la frontera de normalización (`_normalize`), no repartida por cada
  validador, para no reabrir el agujero por olvido en uno nuevo.
- **Función pura y determinista**, sin red ni I/O (coherente con ADR-0010).

## 5. Casos límite y errores
- `None` → "no válido" (no excepción). Es el caso central.
- `""` y `"   "` → "no válido" (ya parcialmente cubierto en `validate_tax_id`; se confirma en todos).
- El `reason` concreto puede ser el de formato inválido existente (p. ej. "Formato de NIF inválido…") o, en
  `validate_tax_id`, "Identificador fiscal vacío"; lo que el contrato fija es `valid=False` + `reason` no vacío.

## 6. Fuera de alcance (no-objetivos)
- **Opción B** (defender contra tipos no-texto arbitrarios): aplazada por decisión de Julio.
- Las funciones de cuadre (`check_tax_line`, `check_invoice_totals`): trabajan con `Decimal`; el caso `None`
  ahí quedó fuera de alcance en BP-1 (hallazgo H2) y no se reabre aquí.
- Cambiar los mensajes de las validaciones que ya funcionan (no es un cambio de textos).

## 7. Notas de verificación
- Tests en `backend/tests/test_ocr_verification.py`, estilo existente. Para C1/C2, `parametrize` sobre los
  cinco validadores con entrada `None`/`""`/`"   "`, aserción de `valid is False` y `reason` no vacío, y que
  la llamada no lanza.
- **Diseño elegido:** `_normalize(value: str | None) -> str` trata `None` como `""`; las firmas públicas de
  los cinco validadores aceptan `str | None` para reflejar que el OCR puede entregar `null`. El resto del
  cuerpo no cambia: `""` recorre el camino de "formato inválido"/"vacío" ya existente.

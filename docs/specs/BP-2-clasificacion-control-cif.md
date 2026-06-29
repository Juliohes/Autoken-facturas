# Spec: BP-2 Clasificación del carácter de control del CIF (N/W/R) — falso positivo + limpieza de K

> Spec-Driven Domain. Esta spec es la **fuente única** que alimenta los tests (TDD) y las auditorías.
> Si algo no está aquí, no se implementa. Aprobada por Julio antes de escribir tests.

- **ID / tarea:** BP-2 (hallazgo de `Auditoria_Autoken_Javi_22-06-2026.md`)
- **Contexto (módulo):** ocr (`backend/src/ocr/verification.py`)
- **ADR relacionados:** ADR-0010 (verificación determinista "tipo DNI"), ADR-0011 (CIF de contraparte)
- **Estado:** aprobada por Julio (2026-06-29)

## 1. Problema y valor de dominio
BP-2 sospechaba que la clasificación del carácter de control del CIF era "demasiado laxa": las claves
`N` (entidades extranjeras), `W` (establecimientos permanentes de no residentes) y `R` (congregaciones)
caen en la rama permisiva "número **o** letra", cuando "probablemente deben exigir letra (según AEAT)".
El propio hallazgo pedía **verificar contra fuente, nunca de memoria**.

## 2. Investigación (fuentes consultadas el 2026-06-28/29)
El carácter de control del CIF se calcula sobre los 7 dígitos (módulo 10); el resultado es un dígito
`0-9` y su letra equivalente en la tabla `JABCDEFGHI`. La duda es **qué claves admiten dígito, cuáles
letra y cuáles ambos**. Las fuentes son **contradictorias**:

| Fuente | N | W | R | Regla "solo letra" |
|---|---|---|---|---|
| Manual AEAT (citado por gestorías; modelo 036) | ambos | ambos | ambos | K, P, Q, S |
| Wikipedia ES (NIF) | letra | letra | letra | P, Q, R, S, W (+ N) |
| **`python-stdnum`** `stdnum/es/cif.py` (impl. de referencia) | ambos | ambos | ambos | *ninguna: acepta ambos para todos los tipos* |

`python-stdnum` resuelve la ambigüedad de forma explícita en su código:
> *"there seems to be conflicting information on which organisation types should have which type of
> check digit (alphabetic or numeric) so we support either here."*

- BOE Orden EHA/451/2008 (composición del NIF de personas jurídicas): define la **estructura** (letra +
  7 dígitos + carácter de control) pero **no** el algoritmo ni la partición por clave del carácter de control.

## 3. Decisión (Julio, 2026-06-29)
**BP-2 se cierra como falso positivo: no se cambia el comportamiento de la clasificación N/W/R.**
- Razón de dominio: esta es la verificación **L1** (estructural) y un falso positivo **bloquea el botón
  "Confirmar y guardar"** (ADR-0011). Endurecer `N`/`W`/`R` a "solo letra" **introduciría** falsos rechazos
  de CIFs válidos de entidades extranjeras y establecimientos permanentes con control numérico, justo lo
  contrario de lo que persigue la regla anti-alucinación. Ante fuentes en conflicto, se mantiene el criterio
  de la implementación de referencia (`python-stdnum`): aceptar ambos.
- Se conserva la estrictez ya existente y no discutida: `P`, `Q`, `S` exigen **letra**; `A`, `B`, `E`, `H`
  exigen **número**.

**Limpieza asociada (sí es cambio):** `K` estaba en `_CIF_LETTER_ONLY` pero NO en `_CIF_TYPES`, así que
un identificador que empieza por `K` se rechazaba por formato antes de llegar a la lógica de control:
`K` en `_CIF_LETTER_ONLY` era **código muerto inalcanzable**. `K` no es una clave de CIF (es un NIF especial
de persona física), por lo que se elimina de `_CIF_LETTER_ONLY`. No hay cambio de comportamiento observable:
un `K…` se sigue rechazando por formato.

## 4. Comportamientos (criterios de aceptación)

### C1 — Las claves ambiguas N/W/R aceptan control numérico o letra
- **Given** un CIF de clave `N`, `W` o `R` cuyo carácter de control es el dígito correcto (p. ej. `N12345674`)
  o su letra equivalente (`N1234567D`)
- **When** se valida el CIF
- **Then** el resultado es válido en ambos casos

### C2 — Las claves de control alfabético siguen exigiendo letra
- **Given** un CIF de clave `P` (control alfabético) con el dígito numérico equivalente en vez de la letra
  (`P12345674` frente al válido `P1234567D`)
- **When** se valida el CIF
- **Then** el numérico es no válido y el alfabético es válido

### C3 — La clave K no es una clave de CIF
- **Given** un identificador que empieza por `K` (`K1234567D`)
- **When** se valida como CIF
- **Then** el resultado es no válido por **formato** (no se procesa como CIF; `K` es un NIF especial de
  persona física, fuera del alcance de `validate_cif`)

## 5. Invariantes y reglas de negocio
- **Anti-falso-positivo en L1:** ante reglas oficiales en conflicto sobre el tipo de control, se acepta el
  superconjunto (número o letra) en vez de arriesgar el rechazo de un CIF real. La verificación de que el
  CIF **existe y pertenece** a la empresa se delega en L3 (AEAT/VIES, ADR-0011), no en L1.
- **`K` no es clave de CIF:** `validate_cif` solo reconoce `ABCDEFGHJNPQRSUVW` como primera letra.
- **Función pura y determinista**, sin red ni I/O (coherente con ADR-0010).

## 6. Fuera de alcance (no-objetivos)
- Cambiar la clasificación de `N`/`W`/`R` a "solo letra" (decisión: NO, ver §3).
- Soporte de NIF especiales de persona física `K`/`L`/`M` en `validate_cif`: fuera de alcance (los gestiona,
  si procede, el dispatcher `validate_tax_id`, que hoy los marca "no reconocido").
- Verificación de existencia/titularidad del CIF (niveles L2/L3/L4 de ADR-0011): otra tarea.

## 7. Notas de verificación
- Tests en `backend/tests/test_ocr_verification.py`, estilo existente: `parametrize` para C1
  (claves × {dígito, letra}); aserción sobre `.valid` y sobre `.reason` en C3.
- Cuerpo de ejemplo `1234567`: dígito de control `4`, letra de control `D` (tabla `JABCDEFGHI`).

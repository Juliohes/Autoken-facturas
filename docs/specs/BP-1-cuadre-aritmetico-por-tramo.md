# Spec: BP-1 Cuadre aritmético por tramo (cerrar el agujero anti-alucinación de los totales)

> Spec-Driven Domain. Esta spec es la **fuente única** que alimenta los tests (TDD) y las 3 auditorías.
> Si algo no está aquí, no se implementa. Aprobada por Julio antes de escribir tests.

- **ID / tarea:** BP-1 (hallazgo de `Auditoria_Autoken_Javi_22-06-2026.md`)
- **Contexto (módulo):** ocr (`backend/src/ocr/verification.py`)
- **ADR relacionados:** ADR-0010 (verificación determinista "tipo DNI")
- **Estado:** aprobada por Julio (2026-06-24)

## 1. Problema y valor de dominio
Hoy `check_invoice_totals` recibe las cuotas de IVA **ya calculadas** y solo comprueba la suma global
(`Σbases + Σcuotas − IRPF = total`); **se fía** de que cada cuota se corresponda con su base. La función que
sí valida `base × IVA% = cuota` (`check_tax_line`) **no la llama nadie** (código muerto, firmas incompatibles).
Resultado: un OCR que lea mal una cuota de un tramo puede colarse a contabilidad si el total global cuadra
(por casualidad o por errores que se compensan). Es el agujero anti-alucinación que BP-1 pide cerrar.

Valor: que el cuadre verifique **cada tramo** además del total, de forma determinista, marcando para revisión
cualquier tramo cuya cuota no se derive de su base y su tipo de IVA.

## 2. Lenguaje ubicuo
- **Tramo (`TaxLine`)**: una línea de impuesto de la factura = (base imponible, tipo de IVA %, cuota de IVA).
  Se modela como value object inmutable con campos nombrados (evita confundir el orden de los importes).
- **Cuadre**: coherencia aritmética. Hay dos niveles: **cuadre de tramo** (`base × IVA% = cuota`) y **cuadre
  global** (`Σbases + Σcuotas − IRPF = total`).
- **Tolerancia**: margen en euros (`DEFAULT_MONEY_TOLERANCE = 0,02`) que absorbe redondeos legales; aplica a
  ambos niveles. Un tipo de IVA NO lleva tolerancia (es exacto); los importes sí.
- **Marcar para revisión**: el resultado es `CheckResult(valid=False, reason=...)` con motivo en español, NO
  una afirmación de fraude; significa "este dato no es fiable, que lo confirme un humano".

## 3. Comportamientos (criterios de aceptación)

### C1 — Una factura coherente cuadra
- **Given** una factura cuyos tramos cumplen cada uno `base × IVA% = cuota` y cuya suma global cuadra con el total
- **When** se verifica el cuadre de la factura
- **Then** el resultado es válido (`valid = True`)

### C2 — Una cuota de tramo que no deriva de su base e IVA% se rechaza  *(el agujero de BP-1)*
- **Given** una factura con un tramo cuya cuota NO es `base × IVA%` (p. ej. base 100, IVA 21%, cuota declarada 25)
- **When** se verifica el cuadre de la factura
- **Then** el resultado es no válido y el `reason` identifica el tramo y el descuadre (hoy esto pasaría como bueno)

### C3 — Errores entre tramos que se compensan en el total se siguen detectando  *(núcleo anti-alucinación)*
- **Given** dos tramos con la cuota mal leída (uno de más y otro de menos) de forma que el **total global sí cuadra**
- **When** se verifica el cuadre de la factura
- **Then** el resultado es no válido, porque al menos un tramo no cuadra; el cuadre global no tapa el error por tramo

### C4 — Descuadre global aunque cada tramo cuadre
- **Given** una factura donde cada tramo cuadra pero la suma global no coincide con el total declarado
- **When** se verifica el cuadre de la factura
- **Then** el resultado es no válido y el `reason` describe el descuadre del total

### C5 — Cuadre global con IRPF
- **Given** una factura con retención IRPF tal que `Σbases + Σcuotas − IRPF = total`, con todos los tramos válidos
- **When** se verifica el cuadre de la factura
- **Then** el resultado es válido

### C6 — Multitramo con tipos de IVA distintos
- **Given** una factura con varios tramos de distintos tipos de IVA, todos válidos y con la suma global correcta
- **When** se verifica el cuadre de la factura
- **Then** el resultado es válido

### C7 — La tolerancia de redondeo se respeta en ambos niveles
- **Given** una diferencia menor o igual a la tolerancia (0,02 €) en un tramo o en el total
- **When** se verifica el cuadre
- **Then** el resultado es válido; una diferencia mayor que la tolerancia es no válida

### C8 — Con varios tramos malos, el motivo identifica el primero (fail-fast)
- **Given** una factura con dos tramos cuya cuota no cuadra
- **When** se verifica el cuadre de la factura
- **Then** el resultado es no válido y el `reason` se refiere al **primer** tramo descuadrado (no se agregan todos)

### C9 — Un importe no finito (NaN / Infinity) se rechaza  *(añadido tras auditoría, hallazgo H1)*
- **Given** una factura con un importe (base, cuota o total) igual a `Decimal("NaN")` o `Decimal("Infinity")`
  (el OCR puede producir un `Decimal` no finito; es un `Decimal` válido por tipo, NO un `None`)
- **When** se verifica el cuadre de la factura
- **Then** el resultado es no válido (nunca `valid=True`) y **nunca lanza una excepción**; el veredicto NO depende
  del estado del contexto decimal global (traps) — la guarda es explícita

## 4. Invariantes y reglas de negocio
- **Anti-alucinación:** una cuota que no se deriva de `base × IVA%` nunca se da por buena, aunque el total
  global cuadre (C3). La validación por tramo no la puede tapar el cuadre global.
- **Importes no finitos:** ningún `Decimal` no finito (`NaN`/`Infinity`) puede dar `valid=True` ni hacer
  estallar la verificación (C9). El veredicto de una función de seguridad no puede depender de estado global
  mutable (los traps del contexto decimal); la comprobación de finitud es explícita.
- **Un solo punto de entrada público de cuadre:** tras esta tarea no debe quedar una función pública que valide
  solo la suma global sin los tramos (no se reabre el agujero). El cuadre global aislado, si se conserva, es
  helper **privado**. `check_tax_line` deja de ser código muerto (la usa el orquestador).
- **Función pura y determinista**, sin red ni I/O (coherente con el módulo y con ADR-0010).
- **Contrato de salida** igual al del módulo: `CheckResult(valid, reason)`; `reason` en español solo si `valid` es False.

## 5. Casos límite y errores
- Tramos en los que la cuota cuadra exactamente (diferencia 0) → válido.
- Diferencia justo en el borde de la tolerancia (== 0,02 → válido; 0,03 → no válido): cubre el hueco TST-3 de
  la auditoría (que un cambio de `>` a `>=` no pase desapercibido).
- IRPF = 0 (caso por defecto) y IRPF > 0.
- Factura sin tramos (`lines == []`): solo aplica el cuadre global (el total debería ser `−IRPF`, normalmente 0).
  Se permite; no es error de formato.
- El `reason` de fallo se asercia explícitamente en los tests (cubre el hueco TST-4): el mensaje es parte del
  contrato porque es lo que ve el usuario en la pantalla de revisión.

## 6. Fuera de alcance (no-objetivos)
- **Recargo de equivalencia**, **IRPF por línea**, y campos `description`/`line_no` en `TaxLine`: NO se añaden
  ahora. El value object `TaxLine` se elige precisamente para poder incorporarlos en S2.8 sin romper llamadores,
  pero esta tarea solo modela `(base, iva_pct, cuota)`.
- **Validación de que el tipo de IVA es un tipo legal vigente** (p. ej. detectar un 15% inexistente): otra tarea.
- **Agregar todos los tramos malos en un solo resultado** (D2): se usa fail-fast (D1). Enriquecer `CheckResult`
  para multi-hallazgo es BP-6, fuera de alcance.
- `check_tax_line` no cambia de firma; sigue siendo la primitiva de tramo.
- **Tipos no-`Decimal`** (`float`, `str`, `None`) en los importes: fuera de alcance (hallazgo H2 de la auditoría).
  Esta tarea solo blinda los `Decimal` no finitos (C9); el contrato sigue siendo que el llamador pasa `Decimal`.

## 7. Notas de verificación (cómo se prueba de extremo a extremo)
- La función es pura: un test por criterio C1-C8 en `backend/tests/test_ocr_verification.py`, estilo existente
  (`parametrize` donde aplique, aserción sobre `.valid` **y** sobre `.reason` en los casos de fallo).
- **Diseño elegido (Opción C):**
  - Nuevo value object: `@dataclass(frozen=True) class TaxLine: base: Decimal; iva_pct: Decimal; cuota: Decimal`.
  - `check_invoice_totals(lines: list[TaxLine], total: Decimal, *, irpf_cuota=Decimal(0), tolerance=DEFAULT_MONEY_TOLERANCE) -> CheckResult`:
    1) por cada tramo, delega en `check_tax_line(base, iva_pct, cuota, tolerance=...)`; al primer fallo, devuelve
       `CheckResult(False, "Tramo N: ...")` (1-based).
    2) si todos los tramos cuadran, comprueba el cuadre global de la suma (helper privado) y devuelve su resultado.
- **Impacto en tests existentes:** los `test_total_*` actuales usan la firma vieja `list[(base, cuota)]`; se
  migran a `list[TaxLine]`. Es esperado: la función pasa a hacer correctamente su trabajo.

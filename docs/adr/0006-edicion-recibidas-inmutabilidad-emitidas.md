# ADR-0006: Facturas recibidas editables (auditado); emitidas inmutables en el futuro Verifactu

- **Estado**: aceptado
- **Fecha**: 2026-06-14
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: PLAN MAESTRO §3.6, §6 (S2/S3), carril §P.1 (Verifactu)

## Contexto
El MVP digitaliza facturas **recibidas y emitidas** vía OCR (registro/contabilización). En paralelo, el
carril futuro Verifactu (RRSIF/AEAT) introducirá la **emisión formal** de facturas, que por ley debe ser
inmutable una vez emitida (solo corregible mediante rectificativas). Hay que fijar desde ya el modelo de
edición para no chocar con Verifactu después.

## Decisión
- **Facturas en el MVP (recibidas y emitidas-registradas)**: los campos son **editables** por el tenant_admin
  tras la confirmación, porque pueden contener errores de OCR o de captura. **Toda edición queda auditada**
  en `audit_log` (quién, cuándo, valor anterior/posterior) y, si es de un valor extraído por IA, genera fila
  en `ocr_corrections`. La confirmación inicial exige checkbox de responsabilidad humana.
- **Facturas emitidas formalmente (futuro módulo `verifactu`)**: serán **inmutables tras la emisión**; cualquier
  cambio se hará mediante **factura rectificativa**, con hash encadenado y registro de eventos. El módulo
  `verifactu` nace como esqueleto + ADR y no bloquea el MVP.

## Alternativas consideradas
- **Inmutabilidad total desde el MVP**: impediría corregir errores de OCR en facturas recibidas, que es
  justo el caso de uso; inadecuado.
- **Edición libre sin auditoría**: incompatible con trazabilidad y con la futura normativa; descartado.

## Consecuencias
- (+) Flexibilidad para corregir datos de OCR en el MVP, con trazabilidad completa.
- (+) Modelo preparado para la inmutabilidad legal de emitidas sin rediseñar el dominio.
- (−) El dominio debe distinguir desde el principio entre "factura registrada" (editable) y futura "factura
  emitida formalmente" (inmutable); se refleja en `invoices.type` y en el diseño de `invoicing`/`verifactu`.

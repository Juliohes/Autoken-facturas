# Dataset de evaluación OCR (bench tarea 1.2)

Ground truth de las 20 facturas reales de `entregas/facturas/` para medir, de forma objetiva y
reproducible, qué motor de **lectura** lee mejor los campos que importan (fecha, importes y, sobre
todo, identificadores fiscales). Alimenta el **ADR-0007** (motor de lectura ganador).

## Estructura

- `ground-truth/<invoice_id>.json`: verdad de referencia por factura. Esquema en
  `backend/src/ocr/eval/models.py` (`GroundTruth`).
- El scorer y el runner viven en `backend/src/ocr/eval/` y `backend/scripts/run_ocr_bench.py`.
  Diseño en `docs/specs/1.2-ocr-eval-scorer.md`.

## Cómo se generó

Transcripción asistida (Claude leyendo cada imagen/PDF) con reglas estrictas: transcribir literal,
`null` si un campo no es legible, **nunca** inventar un identificador. Cada CIF/NIF español se pasó
por el control estructural mód-23 de `ocr/verification.py`: **los 19 identificadores españoles
pasan** (el único que no valida es el EIN de EE. UU. de `vfr-lite`, que no es un ID español). Que
todos cuadren es indicio fuerte de que no hay erratas de dígito.

## Validación pendiente (Julio)

El ground truth está marcado `validated_by_julio: false`. Prioriza estas por confianza baja/media o
por campos ausentes:

| invoice_id | confianza | a revisar |
|---|---|---|
| `wa-182157-1` | **baja** | factura de agua borrosa/girada; CIF del receptor ilegible (`null`) |
| `captura-181602` | media | Coca-Cola sin CIF de emisor visible |
| `captura-181644` | media | Coca-Cola sin CIF de emisor visible |
| `wa-182154-1` | media | Movistar marcada "NOTA INFORMATIVA" (¿es la factura definitiva?) |
| `wa-182154-2` | media | venta BMW 64.028,42 €; CIF de emisor (Ceres) ambiguo → `null` |
| `wa-182154-3` | media | es un **presupuesto**, no una factura; CIF del cliente ausente |
| `wa-182154` | media | Ceres Motor `B10191625` (imagen invertida 180°) |
| `wa-182205-1` | media | **liquidación IVTM** del ayuntamiento, no factura; sin fecha ni CIF emisor |
| `wa-182205` | media | luz Repsol; no se ven CIF de emisor ni receptor en el recorte |

Dos documentos no son facturas comerciales (`wa-182154-3` presupuesto, `wa-182205-1` IVTM). Para el
bench de **lectura** siguen valiendo (son texto a leer), pero conviene que decidas si cuentan para
la métrica final o se excluyen.

## Ejecutar el bench

Desde `backend/`, con el `.env` y el venv:

```bash
.venv/bin/python scripts/run_ocr_bench.py                 # todos los motores cableados
.venv/bin/python scripts/run_ocr_bench.py --engines mistral-ocr-4
```

Imprime el recall de lectura por factura y el agregado por motor (recall global y recall específico
de identificadores fiscales, que es el que más pesa, §11.8).

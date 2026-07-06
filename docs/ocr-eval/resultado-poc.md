# Resultado del POC de lectura OCR (tarea 1.2)

- **Fecha de la corrida**: 2026-07-06 (re-puntuada con el scorer de fecha corregido, issue #44).
- **Dataset**: 20 facturas reales de `entregas/facturas/` (14 JPEG de WhatsApp, 4 PNG de capturas, 2 PDF).
- **Métrica**: recall de **lectura** tolerante al formato (¿aparece en el texto del motor el valor
  del ground truth?), por campo y agregado por motor. El campo decisivo es el **CIF de la
  contraparte** (§11.8): es el de mayor riesgo y el que más falla.
- **Artefacto reproducible**: `docs/ocr-eval/results/bench-2026-07-06.json` (recall global, por
  campo y de CIF, latencia, uso/tokens y **el texto crudo por factura**, para re-puntuar sin volver
  a llamar a las APIs).
- **Cómo reproducir**: `cd backend && .venv/bin/python scripts/run_ocr_bench.py` (usa el `.env`).

## Tabla por motor (20 facturas)

| Motor | Recall global | **Recall CIF** | Total | Neto | Cuota | Fecha | Latencia media | Uso / 20 facturas |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **gemini-3-flash** | **95,2 %** | 90 % | 100 % | 100 % | 100 % | 100 % | 21,5 s | 91 859 tokens (54 427 de "thinking") |
| gemini-3-pro | 92,4 % | **94 %** | 95 % | 94 % | 94 % | 95 % | 58,1 s | 206 374 tokens (106 971 "thinking") |
| azure-docintel | 89,5 % | 71 % | 100 % | 100 % | 100 % | 100 % | **4,8 s** | 20 páginas |
| mistral-ocr-4 | 85,7 % | 77 % | 85 % | 88 % | 94 % | 95 % | **3,6 s** | 20 páginas |
| gpt-5.1 | 63,8 % | 42 % | 85 % | 76 % | 67 % | 63 % | 18,0 s | 34 396 tokens |

Claude (Vertex) **no se ha medido**: el proyecto `autoken-ocr` tiene cuota 0 en el endpoint
`global` (429), pendiente de aumento por Julio. Diferido por decisión de Julio (2026-07-04): ya
dispone de otros OCR.

## Lectura de los resultados

1. **Gemini lidera con claridad.** `gemini-3-flash` es el mejor en recall global (95,2 %), con
   **100 % en fecha, total y cuota**. `gemini-3-pro` va detrás en global pero saca el mejor CIF (94 %).
2. **Flash y Pro empatan en CIF dentro del ruido.** Entre esta corrida y la anterior el CIF de Pro
   se movió (90 % → 94 %) y el de Flash no (90 %): los motores generativos no son deterministas, así
   que una diferencia de ~1 CIF sobre 31 no es significativa. En todo lo demás **Flash gana a Pro**:
   mejor global, 100 % en fecha/total, **2,7× más rápido** (21 s vs 58 s) y **~2,2× menos tokens**.
   No hay razón para pagar Pro en este caso de uso.
3. **DocIntel y Mistral: rápidos y baratos pero flojos en CIF** (71 % y 77 %). Van a ~4 s por página
   y facturan por página (no por token). Buenos candidatos a **segundo motor** del árbitro, pero el
   campo de mayor riesgo se les escapa más que a Gemini.
4. **gpt-5.1 es el más flojo** (CIF 42 %), aun tras optimizarlo (`reasoning_effort=low`,
   `max_completion_tokens` a 16 000 y **rasterizado de los PDF**, issue #16 — antes se quedaba en
   18/20). No compite como motor de lectura.

## Salvedades (por qué el ADR está *propuesto* y no *aceptado*)

- **El ground truth aún no está validado por Julio** (`validated_by_julio: false`). Los 19 CIF
  españoles pasan el mód-23, pero falta su OK (checklist en el README de este directorio).
- **Falta Claude** (cuota 0 en Vertex). Cuando Julio pida el aumento de cuota se relanza `--engines
  claude-vertex` y se actualiza la tabla.

> El recall de fecha, que en la primera corrida salía ~63 % por una limitación del scorer (no de los
> motores), **ya está corregido** (issue #44): `date_matches` reconoce mes textual, año a 2 cifras y
> día sin cero. Por eso esta corrida es la buena.

## Recomendación

**Motor de lectura ganador: `gemini-3-flash`** (recall global líder, 100 % en fecha/total/cuota, CIF
al nivel del mejor dentro del ruido, y muy superior a Pro en coste y latencia). Formalizado en
[ADR-0007](../adr/0007-motor-lectura-ocr.md), en estado *propuesto* hasta validar el ground truth y
medir Claude. Ninguna de las dos salvedades cambia al ganador.

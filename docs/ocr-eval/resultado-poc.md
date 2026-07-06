# Resultado del POC de lectura OCR (tarea 1.2)

- **Fecha de la corrida**: 2026-07-06
- **Dataset**: 20 facturas reales de `entregas/facturas/` (14 JPEG de WhatsApp, 4 PNG de capturas, 2 PDF).
- **Métrica**: recall de **lectura** tolerante al formato (¿aparece en el texto del motor el valor
  del ground truth?), por campo y agregado por motor. El campo decisivo es el **CIF de la
  contraparte** (§11.8): es el de mayor riesgo y el que más falla.
- **Artefacto reproducible**: `docs/ocr-eval/results/bench-2026-07-05.json` (recall global, por
  campo y de CIF, latencia y uso/tokens por motor y por factura).
- **Cómo reproducir**: `cd backend && .venv/bin/python scripts/run_ocr_bench.py` (usa el `.env`).

## Tabla por motor (20 facturas)

| Motor | Recall global | **Recall CIF** | Total | Neto | Cuota | Fecha ⚠️ | Latencia media | Uso / 20 facturas |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| **gemini-3-flash** | **88,6 %** | **90,3 %** | 100 % | 88,2 % | 100 % | 63 % | 20,2 s | 93 365 tokens (55 940 de "thinking") |
| gemini-3-pro | 84,8 % | **90,3 %** | 95 % | 82,4 % | 94,4 % | 58 % | 60,9 s | 205 231 tokens (107 066 "thinking") |
| azure-docintel | 82,9 % | 71,0 % | 100 % | 88,2 % | 100 % | 63 % | **4,5 s** | 20 páginas |
| mistral-ocr-4 | 80,0 % | 77,4 % | 85 % | 82,4 % | 94,4 % | 63 % | **3,5 s** | 20 páginas |
| gpt-5.1 | 61,0 % | 38,7 % | 85 % | 76,5 % | 66,7 % | 53 % | 17,6 s | 35 943 tokens |

Claude (Vertex) **no se ha medido**: el proyecto `autoken-ocr` tiene cuota 0 en el endpoint
`global` (429), pendiente de aumento por Julio (ver [ADR-0007](../adr/0007-motor-lectura-ocr.md) y
la nota de config). Diferido por decisión de Julio (2026-07-04): ya dispone de otros OCR.

## Lectura de los resultados

1. **Gemini lidera con claridad.** `gemini-3-flash` es el mejor en recall global (88,6 %) y empata
   en el primer puesto de CIF (90,3 %) con `gemini-3-pro`, con **100 % en el importe total**.
2. **Flash gana a Pro en todo lo que importa**: mismo CIF, mejor global, **3× más rápido**
   (20 s vs 61 s) y **~2,2× menos tokens**. Pro además tuvo un pico de 410 s en una factura. No hay
   razón para pagar Pro en este caso de uso.
3. **DocIntel y Mistral: rápidos y baratos pero flojos en CIF** (71 % y 77 %). Van a ~4 s por
   página y facturan por página (no por token), pero el campo de mayor riesgo se les escapa más.
4. **gpt-5.1 es el más flojo** (CIF 39 %), incluso tras arreglarlo en esta corrida (`reasoning_effort=low`,
   `max_completion_tokens` a 16 000 y **rasterizado de los PDF**, issue #16 — antes se quedaba en 18/20).
   Mejoró respecto a la corrida previa (era 58 %/32 % de CIF sobre 18 facturas) pero no compite.

## ⚠️ Salvedades (por qué esto es preliminar)

- **El recall de FECHA no es fiable en esta corrida.** Los cuatro motores dan un 63 % **idéntico**
  (12/19). Que motores independientes coincidan al dígito señala al **scorer**, no a los motores:
  `date_variants` solo genera formatos numéricos con día/mes a dos cifras (`18/05/2026`,
  `2026-05-18`...). **No reconoce mes textual** ("18 de mayo de 2026"), ni año a dos cifras, ni día
  sin cero a la izquierda, todos habituales en factura española. Los motores leen la fecha; el
  scorer no la casa. **Issue #44** lo corrige (y guardará el texto crudo en el artefacto para
  re-puntuar sin volver a llamar a las APIs).
- **El ground truth aún no está validado por Julio** (`validated_by_julio: false`). Los 19 CIF
  españoles pasan el mód-23, pero falta su OK (checklist en el README de este directorio).
- **Falta Claude** (cuota 0). Cuando Julio pida el aumento de cuota se relanza `--engines
  claude-vertex` y se actualiza la tabla.

## Recomendación

**Motor de lectura ganador: `gemini-3-flash`** (recall global y de CIF líderes, 100 % en total,
rápido y económico frente a Pro). Formalizado en [ADR-0007](../adr/0007-motor-lectura-ocr.md) con
estado *propuesto* hasta cerrar las tres salvedades (fecha del scorer, validación del GT y medición
de Claude). Ninguna de ellas cambia al ganador: la decisión se apoya en el CIF y el total, que son
sólidos.

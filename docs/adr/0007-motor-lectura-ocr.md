# ADR-0007: Motor de lectura OCR para el POC

- **Estado**: propuesto
- **Fecha**: 2026-07-06
- **Decisores**: Julio (+ Claude Code)

## Contexto

La Fase 1 exige elegir, con **facturas reales**, el motor de **lectura** (transcripción del
documento a texto) sobre el que se construirá el pipeline OCR. La decisión no puede tomarse "de
oídas": el plan (§11.7) manda un bench objetivo y reproducible sobre las 20 facturas de
`entregas/facturas/`, midiendo el recall por campo y, de forma destacada, el **CIF de la
contraparte** (§11.8), que es el campo de mayor riesgo fiscal.

Se construyó una capa común (`OcrEngine` + scorer de recall + runner) y se midieron 5 candidatos.
Detalle numérico en [`docs/ocr-eval/resultado-poc.md`](../ocr-eval/resultado-poc.md); artefacto en
`docs/ocr-eval/results/bench-2026-07-06.json` (corrida re-puntuada con el scorer de fecha corregido,
issue #44).

Resultado (20 facturas, recall global / **CIF**):

- **gemini-3-flash: 95,2 % / 90 %** — líder, 100 % en fecha, total y cuota; 21 s, 92 k tokens.
- gemini-3-pro: 92,4 % / 94 % — mejor CIF, pero 2,7× más lento y ~2,2× más caro que Flash.
- azure-docintel: 89,5 % / 71 % — rapidísimo (4,8 s) y por página, pero flojo en CIF.
- mistral-ocr-4: 85,7 % / 77 % — cabeza de serie de partida; rápido y barato, CIF medio.
- gpt-5.1: 63,8 % / 42 % — el más flojo aun tras optimizarlo (issue #16).

## Decisión

Se adopta **`gemini-3-flash` como motor de lectura del POC**. Gana en recall global y empata en el
primer puesto de CIF con Pro, con 100 % en el importe total, a un coste y latencia muy inferiores a
Pro. En el pipeline de producción (doble motor + árbitro, ADR-0003) será el **motor primario de
lectura**; el segundo motor y el árbitro se deciden en Sprint 2 con este bench como base.

El estado es **propuesto** (no *aceptado*) hasta cerrar dos salvedades, **ninguna de las cuales
cambia al ganador** (Flash lidera el global y va al nivel del mejor CIF dentro del ruido de los
motores generativos):

1. **Ground truth sin validar** por Julio (`validated_by_julio: false`); los 19 CIF españoles pasan
   el mód-23, pero falta su OK.
2. **Claude sin medir**: cuota 0 en Vertex (429, endpoint `global`); pendiente de aumento de cuota.
   Diferido por decisión de Julio (2026-07-04). Al habilitarlo se relanza y se revisa este ADR.

> La tercera salvedad de la primera versión de este ADR (recall de fecha infravalorado por el
> scorer, issue #44) **ya está resuelta**: `date_matches` reconoce mes textual y año a 2 cifras, y
> la corrida se re-puntuó. La fecha pasó de ~63 % a 95-100 % en los motores de calidad.

## Alternativas consideradas

- **gemini-3-pro**: CIF al nivel de Flash (94 % vs 90 %, dentro del ruido) pero sin ninguna ventaja
  que justifique 2,7× la latencia y ~2,2× el coste en tokens (más un pico de 410 s). Descartada como
  primaria.
- **azure-docintel** / **mistral-ocr-4**: las más rápidas y baratas (facturan por página), buenas
  candidatas a **segundo motor** del árbitro, pero su recall de CIF (71 % / 77 %) es insuficiente
  como motor primario del campo de mayor riesgo.
- **gpt-5.1**: descartada como motor de lectura por recall de CIF muy bajo (42 %).
- **PaddleOCR-VL / Qwen3-VL self-hosted**: aún no medidos; se evalúan más adelante si se busca
  abaratar con motor propio (no bloquea el POC).

## Consecuencias

- **Positivas**: motor primario con el mejor recall del campo crítico (CIF 90 %), elegido con datos
  reales y reproducibles. Coste contenido (Flash, no Pro). El bench y el artefacto quedan como base
  objetiva para elegir el segundo motor y el árbitro en Sprint 2.
- **Negativas / riesgos**: dependencia de Vertex (Google) para el motor primario — mitigable con el
  segundo motor del árbitro en otro proveedor (Azure/Mistral). **Residencia de datos**: confirmar
  región UE para Gemini en producción (Vertex `europe-west*`). La decisión es **provisional** hasta
  cerrar las dos salvedades; se pasará a *aceptado* con el GT validado por Julio y (si se decide)
  Claude medido.
- **Multi-tenant / seguridad**: sin impacto directo en aislamiento; el texto de factura es dato de
  tenant y viaja al proveedor de OCR (contemplar en el DPA/residencia).

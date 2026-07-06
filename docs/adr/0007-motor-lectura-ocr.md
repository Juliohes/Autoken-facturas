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
`docs/ocr-eval/results/bench-2026-07-05.json`.

Resultado (20 facturas, recall global / **CIF**):

- **gemini-3-flash: 88,6 % / 90,3 %** — líder, 100 % en total, 20 s, 93 k tokens.
- gemini-3-pro: 84,8 % / 90,3 % — mismo CIF pero 3× más lento y ~2,2× más caro que Flash.
- azure-docintel: 82,9 % / 71,0 % — rapidísimo (4,5 s) y por página, pero flojo en CIF.
- mistral-ocr-4: 80,0 % / 77,4 % — cabeza de serie de partida; rápido y barato, CIF medio.
- gpt-5.1: 61,0 % / 38,7 % — el más flojo aun tras optimizarlo (issue #16).

## Decisión

Se adopta **`gemini-3-flash` como motor de lectura del POC**. Gana en recall global y empata en el
primer puesto de CIF con Pro, con 100 % en el importe total, a un coste y latencia muy inferiores a
Pro. En el pipeline de producción (doble motor + árbitro, ADR-0003) será el **motor primario de
lectura**; el segundo motor y el árbitro se deciden en Sprint 2 con este bench como base.

El estado es **propuesto** (no *aceptado*) hasta cerrar tres salvedades, **ninguna de las cuales
cambia al ganador** (la decisión se apoya en CIF y total, ambos sólidos):

1. **Fecha del scorer** (issue #44): el recall de fecha (63 % idéntico en 4 motores) está
   infravalorado por una limitación del scorer, no por los motores. Al corregirlo subirá para todos.
2. **Ground truth sin validar** por Julio (`validated_by_julio: false`); los 19 CIF españoles pasan
   el mód-23, pero falta su OK.
3. **Claude sin medir**: cuota 0 en Vertex (429, endpoint `global`); pendiente de aumento de cuota.
   Diferido por decisión de Julio (2026-07-04). Al habilitarlo se relanza y se revisa este ADR.

## Alternativas consideradas

- **gemini-3-pro**: mismo CIF que Flash pero sin ninguna ventaja que justifique 3× la latencia y
  ~2,2× el coste en tokens (más un pico de 410 s). Descartada como primaria.
- **azure-docintel** / **mistral-ocr-4**: las más rápidas y baratas (facturan por página), buenas
  candidatas a **segundo motor** del árbitro, pero su recall de CIF (71 % / 77 %) es insuficiente
  como motor primario del campo de mayor riesgo.
- **gpt-5.1**: descartada como motor de lectura por recall de CIF muy bajo (39 %).
- **PaddleOCR-VL / Qwen3-VL self-hosted**: aún no medidos; se evalúan más adelante si se busca
  abaratar con motor propio (no bloquea el POC).

## Consecuencias

- **Positivas**: motor primario con el mejor recall del campo crítico (CIF 90 %), elegido con datos
  reales y reproducibles. Coste contenido (Flash, no Pro). El bench y el artefacto quedan como base
  objetiva para elegir el segundo motor y el árbitro en Sprint 2.
- **Negativas / riesgos**: dependencia de Vertex (Google) para el motor primario — mitigable con el
  segundo motor del árbitro en otro proveedor (Azure/Mistral). **Residencia de datos**: confirmar
  región UE para Gemini en producción (Vertex `europe-west*`). La decisión es **provisional** hasta
  cerrar las tres salvedades; se pasará a *aceptado* al re-puntuar con el scorer arreglado (#44) y
  con el GT validado.
- **Multi-tenant / seguridad**: sin impacto directo en aislamiento; el texto de factura es dato de
  tenant y viaja al proveedor de OCR (contemplar en el DPA/residencia).

# ADR-0003: Pipeline OCR de 4 capas con doble motor, árbitro y regla anti-alucinación

- **Estado**: aceptado (la combinación concreta de motores se fija en ADR-0007 tras la Fase 1)
- **Fecha**: 2026-06-14
- **Decisores**: Julio (+ Claude Code)
- **Relacionado**: PLAN MAESTRO §4; regla de oro nº 4

## Contexto
El corazón del producto es extraer datos de facturas con alta fiabilidad. El mayor riesgo es la
**alucinación**: que la IA "complete" un CIF, nombre o importe no legible y ese valor inventado llegue a la
UI como si fuera leído. Hay que maximizar precisión y, sobre todo, no inventar nunca.

## Decisión
Pipeline de **4 capas**:
1. **Captura guiada en cliente** (PWA): nitidez (varianza de Laplaciano), encuadre y exposición; auto-captura
   y rechazo de imágenes malas (no viajan al servidor).
2. **Preprocesado en servidor** (worker): deskew, recorte, normalización; PDF con texto nativo → extracción
   directa sin OCR; ClamAV + MIME real.
3. **Doble motor + árbitro + validación determinista**: Motor A (Azure Document Intelligence
   `prebuilt-invoice`) + Motor B (LLM de visión con prompt estricto "si no es legible, `null`"); árbitro por
   campo; validación SIN IA (dígito de control CIF/NIF, cuadre aritmético, fecha plausible, IRPF solo si
   aparece literalmente).
4. **Mejora continua**: cada corrección humana → `ocr_corrections`; informe mensual de precisión por campo y
   motor.
- **Regla anti-alucinación (innegociable)**: campo no legible o sin acuerdo que pase validación = `null` +
  marca roja "Revisar". Confianza baja = amarillo. Verificado con test (factura con CIF tapado → `null`).

## Alternativas consideradas
- **Un solo motor**: más barato pero sin contraste; un error del motor pasa directo. El árbitro de dos
  motores + validación determinista reduce errores.
- **Confiar en la confianza del motor sin validación determinista**: insuficiente (caso IRPF fantasma de Alex
  Distribuciones); las reglas deterministas son la red de seguridad.

## Consecuencias
- (+) Alta precisión y, sobre todo, cero valores inventados en la UI.
- (+) Dataset de mejora continua para decisiones basadas en datos.
- (−) Coste por factura (< 0,04 €) y latencia de dos motores; se registra `cost` por extracción.
- (−) Más complejidad; la combinación final de motores se decide con datos reales en la Fase 1 (ADR-0007).

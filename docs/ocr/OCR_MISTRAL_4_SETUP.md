# Mistral OCR 4 — configuración y uso (motor de lectura, Fase 1)

Motor de lectura **cabeza de serie** del bench OCR (decisión de Julio, 2026-07-01). El ganador
formal de producción lo decide el bench con las 20 facturas reales (ADR-0007). Spec del motor:
`docs/specs/1.2-mistral-ocr4-engine.md`.

## 1. Obtener la API key de Mistral
1. Entra en **console.mistral.ai** e inicia sesión.
2. Añade un método de pago (la API OCR es de pago: ~4 $/1.000 páginas, 2 $ en modo batch).
3. Menú **"API Keys"** → **"Create new key"** → copia la clave (solo se muestra una vez).

## 2. Variables de entorno (`.env`, NUNCA en el repo)
```
MISTRAL_API_KEY=sk-...            # secreto (ya puesto)
MISTRAL_OCR_MODEL=mistral-ocr-4-0 # id de modelo verificado (alias: mistral-ocr-latest)
MISTRAL_OCR_TIMEOUT=60            # segundos
```
> Nota: en `.env.example` conviene reflejar `MISTRAL_OCR_MODEL` y `MISTRAL_OCR_TIMEOUT` (sin valor
> secreto) para documentar el contrato. El `.env.example` lo mantiene Julio (el entorno de Claude
> Code no accede a ficheros `.env*`).

## 3. Uso básico (código)
```python
from ocr.engines import build_default_reading_engine
from shared.config import get_settings

engine = build_default_reading_engine(get_settings())   # cabeza de serie = Mistral OCR 4
result = await engine.extract("entregas/facturas/factura-2.pdf")

print(result.text)          # markdown de todas las páginas
print(len(result.pages))    # páginas
print(result.raw)           # respuesta cruda del proveedor (bloques, bbox, confidencias)
```
Errores: cualquier fallo (credenciales, timeout, tipo no soportado, error de API) llega como
`MistralOcrError` (subclase de `OcrError`); nunca una excepción cruda del SDK.

## 4. Prueba real contra una factura (la lanza Julio)
Los tests automáticos van con la API **mockeada** (sin red). La validación real, con una de las 20
facturas, se hace a mano con la key del `.env`:
```bash
cd backend && source .venv/bin/activate
python scripts/smoke_mistral_ocr.py ../entregas/facturas/factura-2.pdf
```
Debe imprimir el modelo, el nº de páginas y un extracto del texto.

## 5. Limitaciones conocidas
- **Solo lectura estructural** (texto/markdown + bloques/bbox/confidencias). La verificación
  determinista de CIF/importes/fechas ("tipo DNI") es otra capa (`ocr/verification.py`).
- **`batch_extract`** aquí es concurrencia local (`asyncio.gather`), NO el endpoint batch de
  Mistral; el batch nativo (más barato) se evaluará en el bench si compensa.
- El **parseo tipado fino de bloques/bounding boxes** no está en el motor: se conserva todo en
  `OcrResult.raw` y lo explotará el scorer del bench.
- Tipos de fichero soportados: PDF, JPEG, PNG, WEBP (las 20 facturas del POC entran).

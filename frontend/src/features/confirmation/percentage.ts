// Formateo del tipo de IVA (%) para el input editable del tramo (spec §2, C8-bis).
//
// Por qué existe este fichero aparte de `formState.ts` / `taxCellToInput`:
// el OCR (o el humano al escribir) puede entregar el tipo de IVA como `21`, `21.0`,
// `21.00` o incluso `"21,0"` (coma decimal). Julio pidió explícitamente que el % de
// IVA se muestre SIEMPRE sin el ".0"/",0" superfluo (ej. "21%", nunca "21,0%"),
// mientras que el resto de importes (base, cuota, totales) mantienen sus decimales
// tal cual vienen. Por eso esta normalización se aplica solo a `iva_pct` y vive en
// su propio módulo puro y testeable, sin tocar `taxCellToInput` (que siguen usando
// `base`/`cuota`).
//
// Regla exacta: si el valor es un número entero (incluida su representación con
// decimales en cero: 21.0, 21.00, "21,0"), se muestra sin parte decimal. Si tiene
// decimales no nulos (ej. un tipo reducido no entero), se conservan tal cual —
// nunca se inventa ni se redondea un valor real.

/** Convierte "21,0" / "21.00" / 21 / null a un `number` o `null` si no es parseable. */
function parsePercentage(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null
  }
  const trimmed = value.trim()
  if (trimmed === '') return null
  // Admite tanto coma (formato ES) como punto (formato OCR/JSON) como separador decimal.
  const normalized = trimmed.replace(',', '.')
  const parsed = Number(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Formatea el tipo de IVA para el input del tramo: sin decimales cuando el valor
 * es un número entero (21, 21.0, 21.00, "21,0" -> "21"); conserva los decimales
 * reales en caso contrario (ej. 4.5 -> "4.5"). Valor no parseable o ausente -> ''
 * (campo no leído, regla 4: no se inventa).
 *
 * Nota de implementación: el truco no es un `if` sobre enteros — es convertir el
 * valor a `number` (`parsePercentage`) antes de volver a stringificarlo. `String()`
 * sobre un `number` de JS ya descarta los ceros decimales sobrantes (`String(21.0)
 * === '21'`); el bug real ("21,0%") solo aparece si el valor viaja como texto
 * literal con esos ceros (p. ej. `"21,0"` del OCR) y se muestra sin pasar por
 * `Number()` primero — que es exactamente lo que hacía `taxCellToInput`.
 */
export function formatIvaPercentage(value: number | string | null | undefined): string {
  const parsed = parsePercentage(value)
  return parsed === null ? '' : String(parsed)
}

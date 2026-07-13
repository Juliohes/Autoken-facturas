// Lógica pura del color de confianza por campo (spec §2, C2). Separada de la
// presentación para poder probarla sin renderizar.
import type { Confidence } from './types'

/** Marca visual de un campo según su confianza. */
export type ConfidenceMark = 'ok' | 'dudoso' | 'no_leido'

/**
 * Traduce la confianza del OCR a la marca visual (C2):
 * - `alta` -> `ok` (sin aviso).
 * - `media` -> `dudoso` (amarillo).
 * - `baja`, ausente o `null` -> `no_leido` (rojo): anti-alucinación, un campo no
 *   leído se marca en rojo, nunca en blanco como si fuera correcto (regla 4).
 */
export function confidenceMark(confidence: Confidence | undefined): ConfidenceMark {
  if (confidence === 'alta') return 'ok'
  if (confidence === 'media') return 'dudoso'
  return 'no_leido'
}

/** Etiqueta legible de la marca (vacía cuando no hay aviso). */
export function confidenceLabel(mark: ConfidenceMark): string {
  if (mark === 'dudoso') return 'Dudoso'
  if (mark === 'no_leido') return 'No leído'
  return ''
}

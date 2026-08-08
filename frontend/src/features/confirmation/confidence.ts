// Lógica pura del color de confianza por campo (spec §2, C2). Separada de la
// presentación para poder probarla sin renderizar.
import type { Confidence } from './types'

/** Marca visual de un campo según su confianza y si tiene valor. */
export type ConfidenceMark = 'ok' | 'dudoso' | 'revisar' | 'no_leido'

/**
 * Traduce la confianza del OCR (y si el campo tiene valor) a la marca visual (C2; ampliado spec
 * S6.1 C20-C24):
 * - Sin valor (`hasValue` falso) -> `no_leido` (rojo): el campo no se leyó de verdad, sea cual sea
 *   la confianza declarada (anti-alucinación, regla 4).
 * - Con valor y `alta` -> `ok` (sin aviso).
 * - Con valor y `media` -> `dudoso` (amarillo).
 * - Con valor y `baja`/ausente -> `revisar` ("Dudoso, revisar"): el motor propuso un valor pero no
 *   está seguro — NO es "no leído" (hallazgo real 2026-08-07: mostrar "No leído" junto a un valor
 *   confundía, parecía que no se había leído nada).
 */
export function confidenceMark(confidence: Confidence | undefined, hasValue: boolean): ConfidenceMark {
  if (!hasValue) return 'no_leido'
  if (confidence === 'alta') return 'ok'
  if (confidence === 'media') return 'dudoso'
  return 'revisar'
}

/** Etiqueta legible de la marca (vacía cuando no hay aviso). */
export function confidenceLabel(mark: ConfidenceMark): string {
  if (mark === 'dudoso') return 'Dudoso'
  if (mark === 'revisar') return 'Dudoso, revisar'
  if (mark === 'no_leido') return 'No leído'
  return ''
}

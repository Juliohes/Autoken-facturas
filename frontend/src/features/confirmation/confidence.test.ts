// Tests del color de confianza por campo (spec §2, C2; ampliado spec S6.1 C20-C24).
import { describe, expect, it } from 'vitest'

import { confidenceLabel, confidenceMark } from './confidence'

describe('confidenceMark', () => {
  it('alta -> ok (sin marca)', () => {
    expect(confidenceMark('alta', true)).toBe('ok')
    expect(confidenceLabel('ok')).toBe('')
  })

  it('media CON valor -> dudoso (amarillo)', () => {
    // spec: S6.1 C22 — sin cambios respecto al comportamiento ya existente.
    expect(confidenceMark('media', true)).toBe('dudoso')
    expect(confidenceLabel('dudoso')).toBe('Dudoso')
  })

  it('media SIN valor -> no leído (C21 manda sobre C22: la ausencia del valor es más fuerte)', () => {
    expect(confidenceMark('media', false)).toBe('no_leido')
  })

  it('baja o ausente CON valor -> "Dudoso, revisar" (spec: S6.1 C20)', () => {
    expect(confidenceMark('baja', true)).toBe('revisar')
    expect(confidenceMark(null, true)).toBe('revisar')
    expect(confidenceMark(undefined, true)).toBe('revisar')
    expect(confidenceLabel('revisar')).toBe('Dudoso, revisar')
  })

  it('valor ausente -> "No leído", sea cual sea la confianza (spec: S6.1 C21)', () => {
    expect(confidenceMark('baja', false)).toBe('no_leido')
    expect(confidenceMark(null, false)).toBe('no_leido')
    expect(confidenceMark(undefined, false)).toBe('no_leido')
    expect(confidenceLabel('no_leido')).toBe('No leído')
  })
})

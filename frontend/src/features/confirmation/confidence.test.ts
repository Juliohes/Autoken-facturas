// Tests del color de confianza por campo (spec §2, C2).
import { describe, expect, it } from 'vitest'

import { confidenceLabel, confidenceMark } from './confidence'

describe('confidenceMark', () => {
  it('alta -> ok (sin marca)', () => {
    expect(confidenceMark('alta')).toBe('ok')
    expect(confidenceLabel('ok')).toBe('')
  })

  it('media -> dudoso (amarillo)', () => {
    expect(confidenceMark('media')).toBe('dudoso')
    expect(confidenceLabel('dudoso')).toBe('Dudoso')
  })

  it('baja, null o ausente -> no_leido (rojo)', () => {
    expect(confidenceMark('baja')).toBe('no_leido')
    expect(confidenceMark(null)).toBe('no_leido')
    expect(confidenceMark(undefined)).toBe('no_leido')
    expect(confidenceLabel('no_leido')).toBe('No leído')
  })
})

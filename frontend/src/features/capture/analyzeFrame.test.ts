import { describe, expect, it } from 'vitest'

import { analysisDimensions } from './analyzeFrame'

describe('still analysis sizing (R-009)', () => {
  it('reduce solo la copia de análisis y conserva la proporción', () => {
    expect(analysisDimensions(4000, 3000)).toEqual({ width: 1600, height: 1200 })
    expect(analysisDimensions(1200, 800)).toEqual({ width: 1200, height: 800 })
  })

  it('reduce también un still vertical sin intercambiar sus ejes', () => {
    expect(analysisDimensions(2160, 4096)).toEqual({ width: 844, height: 1600 })
  })
})

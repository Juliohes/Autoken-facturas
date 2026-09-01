import { describe, expect, it } from 'vitest'

import { startCaptureTiming } from './capturePerformance'

describe('capturePerformance (R-052)', () => {
  it('C12: crea una medida local por cada fase de captura sin enviar datos', () => {
    const timing = startCaptureTiming()
    timing.mark('frame')
    timing.mark('analysis')
    timing.mark('processing')
    timing.mark('preview')

    const names = performance.getEntriesByType('measure').map((entry) => entry.name)
    expect(names).toEqual(expect.arrayContaining([
      'autoken.capture.frame',
      'autoken.capture.analysis',
      'autoken.capture.processing',
      'autoken.capture.preview',
    ]))
  })
})

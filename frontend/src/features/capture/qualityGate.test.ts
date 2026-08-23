import { describe, expect, it } from 'vitest'

import { evaluateQualityGate } from './qualityGate'
import type { CaptureQuality } from './types'

function quality(overrides: Partial<CaptureQuality & { stableLongEnough: boolean }> = {}) {
  return {
    sharpness: 180,
    meanLuminance: 128,
    darkPixelRatio: 0.01,
    brightPixelRatio: 0.01,
    areaRatio: 0.55,
    detectionConfidence: 0.9,
    stabilityScore: 1,
    perspectiveScore: 1.1,
    clipped: false,
    stableLongEnough: true,
    ...overrides,
  }
}

describe('evaluateQualityGate', () => {
  it.each([
    [{ detectionConfidence: 0, areaRatio: 0 }, 'no_document'],
    [{ detectionConfidence: 0.5 }, 'low_confidence'],
    [{ areaRatio: 0.1 }, 'too_small'],
    [{ clipped: true }, 'clipped'],
    [{ sharpness: 20 }, 'blurry'],
    [{ meanLuminance: 10, darkPixelRatio: 0.3 }, 'too_dark'],
    [{ meanLuminance: 250, brightPixelRatio: 0.3 }, 'too_bright'],
    [{ perspectiveScore: 2.4 }, 'perspective_extreme'],
    [{ stableLongEnough: false }, 'moving'],
  ])('rechaza la captura con razón %s', (overrides, reason) => {
    expect(evaluateQualityGate(quality(overrides))).toEqual({ ready: false, reason })
  })

  it('permite AUTO cuando todas las señales cumplen el umbral', () => {
    expect(evaluateQualityGate(quality())).toEqual({ ready: true, reason: 'ready' })
  })
})

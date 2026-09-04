import { describe, expect, it } from 'vitest'

import {
  normalizedPointToScreen,
  screenPointToNormalized,
  screenPointToSource,
  sourcePointToScreen,
  type CoordinateSpace,
} from './coordinates'

const PORTRAIT_VIEW: CoordinateSpace = {
  sourceWidth: 1920,
  sourceHeight: 1080,
  containerWidth: 390,
  containerHeight: 844,
}

describe('coordinates (object-cover)', () => {
  it('compensa el recorte horizontal de object-cover', () => {
    expect(sourcePointToScreen({ x: 960, y: 540 }, PORTRAIT_VIEW)).toEqual({ x: 195, y: 422 })
    expect(sourcePointToScreen({ x: 0, y: 0 }, PORTRAIT_VIEW).x).toBeLessThan(0)
  })

  it('mantiene round-trip entre fuente y pantalla', () => {
    const source = { x: 1200, y: 700 }
    const screen = sourcePointToScreen(source, PORTRAIT_VIEW)
    expect(screenPointToSource(screen, PORTRAIT_VIEW)).toEqual({ x: expect.closeTo(source.x), y: expect.closeTo(source.y) })
  })

  it('convierte coordenadas normalizadas usando la misma transformación', () => {
    const normalized = { x: 0.625, y: 0.5 }
    const screen = normalizedPointToScreen(normalized, PORTRAIT_VIEW)
    expect(screenPointToNormalized(screen, PORTRAIT_VIEW)).toEqual(normalized)
  })
})

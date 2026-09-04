import { describe, expect, it } from 'vitest'

import { advanceStability, INITIAL_STABILITY } from './stability'

const corners = [
  { x: 100, y: 50 },
  { x: 540, y: 50 },
  { x: 540, y: 430 },
  { x: 100, y: 430 },
]

describe('advanceStability', () => {
  it('requiere cuatro frames válidos y 700 ms antes de estabilizar', () => {
    let state = INITIAL_STABILITY
    for (const at of [0, 200, 400]) {
      const result = advanceStability(state, { corners, areaRatio: 0.55 }, at, 640, 480)
      state = result.state
      expect(result.stableLongEnough).toBe(false)
    }

    const result = advanceStability(state, { corners, areaRatio: 0.55 }, 700, 640, 480)
    expect(result.stableLongEnough).toBe(true)
    expect(result.state.frames).toBe(4)
  })

  it('reinicia el historial si el documento se mueve o cambia demasiado de área', () => {
    const first = advanceStability(INITIAL_STABILITY, { corners, areaRatio: 0.55 }, 0, 640, 480)
    const moved = advanceStability(first.state, {
      corners: corners.map((corner) => ({ ...corner, x: corner.x + 20 })),
      areaRatio: 0.55,
    }, 200, 640, 480)
    expect(moved.state.frames).toBe(1)
    expect(moved.stableLongEnough).toBe(false)

    const resized = advanceStability(first.state, { corners, areaRatio: 0.8 }, 200, 640, 480)
    expect(resized.state.frames).toBe(1)
    expect(resized.stableLongEnough).toBe(false)
  })
})

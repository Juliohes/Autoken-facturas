import { renderHook, act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useAutoCapture } from './useAutoCapture'
import type { FrameAnalysis } from './types'

const corners = [
  { x: 100, y: 50 },
  { x: 540, y: 50 },
  { x: 540, y: 430 },
  { x: 100, y: 430 },
]

const validAnalysis: FrameAnalysis = {
  sharpness: 180,
  corners,
  detectionConfidence: 0.9,
  areaRatio: 0.55,
  meanLuminance: 128,
  darkPixelRatio: 0.01,
  brightPixelRatio: 0.01,
  clipped: false,
  perspectiveScore: 1.1,
}
const incompleteAnalysis = { ...validAnalysis, meanLuminance: undefined }

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('useAutoCapture', () => {
  it('arma AUTO tras cuatro frames válidos y dispara una sola vez tras la confirmación', () => {
    vi.useFakeTimers()
    vi.spyOn(performance, 'now')
    const onAutoCapture = vi.fn(() => true)
    const { result, rerender } = renderHook(
      ({ analysis }) => useAutoCapture({ analysis, enabled: true, sourceWidth: 640, sourceHeight: 480, onAutoCapture }),
      { initialProps: { analysis: null as FrameAnalysis | null } },
    )

    for (const at of [0, 200, 400, 700]) {
      vi.mocked(performance.now).mockReturnValue(at)
      rerender({ analysis: { ...validAnalysis, corners: corners.map((corner) => ({ ...corner })) } })
    }

    expect(result.current.phase).toBe('auto_armed')
    expect(result.current.decision).toEqual({ ready: true, reason: 'ready' })
    act(() => vi.advanceTimersByTime(349))
    expect(onAutoCapture).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(onAutoCapture).toHaveBeenCalledOnce()
  })

  it('un cambio a MANUAL cancela el armado y conserva disponible la captura manual', () => {
    vi.useFakeTimers()
    const onAutoCapture = vi.fn(() => true)
    const { result } = renderHook(() => useAutoCapture({
      analysis: validAnalysis,
      enabled: true,
      sourceWidth: 640,
      sourceHeight: 480,
      onAutoCapture,
    }))

    act(() => result.current.setMode('manual'))
    expect(result.current.mode).toBe('manual')
    expect(result.current.phase).toBe('scanning')
    act(() => vi.advanceTimersByTime(1000))
    expect(onAutoCapture).not.toHaveBeenCalled()
  })

  it('no arma AUTO cuando faltan señales de calidad reales', () => {
    const { result } = renderHook(() => useAutoCapture({
      analysis: incompleteAnalysis,
      enabled: true,
      sourceWidth: 640,
      sourceHeight: 480,
      onAutoCapture: vi.fn(() => true),
    }))

    expect(result.current.phase).toBe('scanning')
    expect(result.current.decision).toEqual({ ready: false, reason: 'no_document' })
  })
})

// Tests de comportamiento de la orquestación de captura (S2.2, C4-C7/C10). Análisis de frame
// inyectado a mano (sin OpenCV real, eso ya se prueba en opencv/blur.test.ts y
// opencv/documentEdges.test.ts) — aquí solo importa la decisión de estado, no el algoritmo.
import { describe, expect, it } from 'vitest'

import { captureReducer, INITIAL_CAPTURE_STATE } from './captureLoop'
import type { FrameAnalysis } from './types'

const THRESHOLD = 100
const CORNERS = [
  { x: 10, y: 10 },
  { x: 90, y: 10 },
  { x: 90, y: 90 },
  { x: 10, y: 90 },
]

function analysis(over: Partial<FrameAnalysis> = {}): FrameAnalysis {
  return { sharpness: 200, corners: CORNERS, ...over }
}

describe('captureReducer', () => {
  it('S6.10 C1: analizar un fotograma nítido y encuadrado nunca toma una foto por sí solo', () => {
    const next = captureReducer(
      INITIAL_CAPTURE_STATE,
      { type: 'frame_analyzed', analysis: analysis({ sharpness: 150, corners: CORNERS }) },
      THRESHOLD,
    )
    expect(next).toEqual(INITIAL_CAPTURE_STATE)
  })

  it('C5: un frame borroso se queda en "live"', () => {
    const next = captureReducer(
      INITIAL_CAPTURE_STATE,
      { type: 'frame_analyzed', analysis: analysis({ sharpness: 10, corners: CORNERS }) },
      THRESHOLD,
    )
    expect(next).toEqual(INITIAL_CAPTURE_STATE)
  })

  it('C6: un frame nítido sin documento se queda en "live"', () => {
    const next = captureReducer(
      INITIAL_CAPTURE_STATE,
      { type: 'frame_analyzed', analysis: analysis({ sharpness: 150, corners: null }) },
      THRESHOLD,
    )
    expect(next).toEqual(INITIAL_CAPTURE_STATE)
  })

  it('un fotograma analizado tras una captura manual no cambia nada', () => {
    const captured = captureReducer(
      INITIAL_CAPTURE_STATE,
      { type: 'frame_analyzed', analysis: analysis({ sharpness: 150, corners: CORNERS }) },
      THRESHOLD,
    )
    const next = captureReducer(
      captured,
      { type: 'frame_analyzed', analysis: analysis({ sharpness: 300, corners: CORNERS }) },
      THRESHOLD,
    )
    expect(next).toBe(captured)
  })

  it('C7: captura manual con nitidez baja avisa (wasBlurry) pero no bloquea', () => {
    const next = captureReducer(
      INITIAL_CAPTURE_STATE,
      { type: 'manual_capture', analysis: analysis({ sharpness: 10, corners: null }) },
      THRESHOLD,
    )
    expect(next).toEqual({ phase: 'captured', corners: null, wasBlurry: true })
  })

  it('C7: captura manual con nitidez suficiente no avisa', () => {
    const next = captureReducer(
      INITIAL_CAPTURE_STATE,
      { type: 'manual_capture', analysis: analysis({ sharpness: 200, corners: CORNERS }) },
      THRESHOLD,
    )
    expect(next).toEqual({ phase: 'captured', corners: CORNERS, wasBlurry: false })
  })

  it('captura manual sin análisis disponible (fallback de fichero, C3) no avisa de nada', () => {
    const next = captureReducer(INITIAL_CAPTURE_STATE, { type: 'manual_capture', analysis: null }, THRESHOLD)
    expect(next).toEqual({ phase: 'captured', corners: null, wasBlurry: false })
  })

  it('C10: "retake" vuelve siempre a "live"', () => {
    const captured = captureReducer(
      INITIAL_CAPTURE_STATE,
      { type: 'manual_capture', analysis: analysis() },
      THRESHOLD,
    )
    expect(captureReducer(captured, { type: 'retake' }, THRESHOLD)).toEqual(INITIAL_CAPTURE_STATE)
  })
})

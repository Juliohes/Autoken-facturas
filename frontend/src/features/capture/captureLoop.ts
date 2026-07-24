// Orquestación de la captura (S2.2 decisiones 4/5/6/7), pura y sin OpenCV/cámara: decide cuándo
// dispara la auto-captura y qué pasa con cada acción, a partir de resultados de análisis ya
// calculados. Se prueba inyectando `FrameAnalysis` de mentira, sin cargar el runtime WASM.
import type { Corner, FrameAnalysis } from './types'

// Umbral de nitidez por defecto para la auto-captura (spec §3 C4/C5): varianza del Laplaciano de
// una imagen ya en foco suele superar ampliamente este valor; una borrosa se queda muy por debajo
// (ver `opencv/blur.test.ts` para el contraste real nítida-vs-borrosa contra el mismo umbral).
export const DEFAULT_SHARPNESS_THRESHOLD = 100

export type CaptureState =
  | { phase: 'live' }
  | { phase: 'captured'; corners: Corner[] | null; wasBlurry: boolean }

export type CaptureAction =
  | { type: 'frame_analyzed'; analysis: FrameAnalysis }
  | { type: 'manual_capture'; analysis: FrameAnalysis | null }
  | { type: 'retake' }

export const INITIAL_CAPTURE_STATE: CaptureState = { phase: 'live' }

/** Un frame dispara la auto-captura solo si es nítido Y tiene un documento reconocible (C4-C6):
 * ambas condiciones a la vez, nunca una sola. */
export function shouldAutoCapture(analysis: FrameAnalysis, sharpnessThreshold: number): boolean {
  return analysis.sharpness >= sharpnessThreshold && analysis.corners !== null
}

export function captureReducer(
  state: CaptureState,
  action: CaptureAction,
  sharpnessThreshold: number = DEFAULT_SHARPNESS_THRESHOLD,
): CaptureState {
  switch (action.type) {
    case 'frame_analyzed': {
      if (state.phase !== 'live') return state
      if (!shouldAutoCapture(action.analysis, sharpnessThreshold)) return state
      return { phase: 'captured', corners: action.analysis.corners, wasBlurry: false }
    }
    case 'manual_capture': {
      if (state.phase !== 'live') return state
      const analysis = action.analysis
      return {
        phase: 'captured',
        corners: analysis?.corners ?? null,
        wasBlurry: analysis !== null && analysis.sharpness < sharpnessThreshold,
      }
    }
    case 'retake':
      return INITIAL_CAPTURE_STATE
  }
}

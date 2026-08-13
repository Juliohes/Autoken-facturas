// Orquestación de la captura manual, pura y sin OpenCV/cámara. El análisis solo acompaña al disparo
// explícito de la persona para preservar la decisión consciente de tomar la foto.
import type { Corner, FrameAnalysis } from './types'

// Umbral de nitidez para avisar tras una captura manual.
export const DEFAULT_SHARPNESS_THRESHOLD = 100

export type CaptureState =
  | { phase: 'live' }
  | { phase: 'captured'; corners: Corner[] | null; wasBlurry: boolean }

export type CaptureAction =
  | { type: 'frame_analyzed'; analysis: FrameAnalysis }
  | { type: 'manual_capture'; analysis: FrameAnalysis | null }
  | { type: 'retake' }

export const INITIAL_CAPTURE_STATE: CaptureState = { phase: 'live' }

export function captureReducer(
  state: CaptureState,
  action: CaptureAction,
  sharpnessThreshold: number = DEFAULT_SHARPNESS_THRESHOLD,
): CaptureState {
  switch (action.type) {
    case 'frame_analyzed': {
      return state
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

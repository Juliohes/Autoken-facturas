// Orquestación de la captura manual, pura y sin OpenCV/cámara. El análisis solo acompaña al disparo
// explícito de la persona para preservar la decisión consciente de tomar la foto.
import type { Corner, FrameAnalysis } from './types'

export type CaptureMode = 'auto' | 'manual'

export type ScannerPhase =
  | 'scanning'
  | 'valid'
  | 'stabilizing'
  | 'auto_armed'
  | 'capturing'
  | 'still_processing'
  | 'preview'
  | 'uploading'
  | 'accepted'
  | 'error'

export interface ScannerState {
  phase: ScannerPhase
  mode: CaptureMode
  stableSince: number | null
  stableFrames: number
  autoArmed: boolean
  captureLocked: boolean
}

export type ScannerAction =
  | { type: 'quality_evaluated'; ready: boolean; stableLongEnough: boolean; at?: number }
  | { type: 'mode_changed'; mode: CaptureMode }
  | { type: 'capture_started' }
  | { type: 'still_processing' }
  | { type: 'preview' }
  | { type: 'uploading' }
  | { type: 'accepted' }
  | { type: 'error' }
  | { type: 'retake' }

export const INITIAL_SCANNER_STATE: ScannerState = {
  phase: 'scanning',
  mode: 'auto',
  stableSince: null,
  stableFrames: 0,
  autoArmed: false,
  captureLocked: false,
}

function resetStability(state: ScannerState, mode: CaptureMode): ScannerState {
  return { ...state, mode, phase: 'scanning', stableSince: null, stableFrames: 0, autoArmed: false }
}

export function scannerReducer(state: ScannerState, action: ScannerAction): ScannerState {
  switch (action.type) {
    case 'mode_changed':
      return resetStability(state, action.mode)
    case 'quality_evaluated': {
      if (!action.ready) return { ...resetStability(state, state.mode), captureLocked: state.captureLocked }
      const stableSince = state.stableSince ?? action.at ?? 0
      const stableFrames = state.stableFrames + 1
      if (state.mode === 'manual') return { ...state, phase: 'valid', stableSince, stableFrames, autoArmed: false }
      if (!action.stableLongEnough) return { ...state, phase: 'stabilizing', stableSince, stableFrames, autoArmed: false }
      return { ...state, phase: 'auto_armed', stableSince, stableFrames, autoArmed: true }
    }
    case 'capture_started':
      return state.captureLocked ? state : { ...state, phase: 'capturing', captureLocked: true, autoArmed: false }
    case 'still_processing':
      return { ...state, phase: 'still_processing' }
    case 'preview':
      return { ...state, phase: 'preview' }
    case 'uploading':
      return { ...state, phase: 'uploading' }
    case 'accepted':
      return { ...state, phase: 'accepted', captureLocked: false }
    case 'error':
      return { ...state, phase: 'error', captureLocked: false }
    case 'retake':
      return { ...resetStability(state, state.mode), captureLocked: false }
  }
}

export interface CaptureLockRef {
  current: boolean
}

export function acquireCaptureLock(lock: CaptureLockRef): boolean {
  if (lock.current) return false
  lock.current = true
  return true
}

export function releaseCaptureLock(lock: CaptureLockRef): void {
  lock.current = false
}

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

import { useEffect, useRef, useReducer, useState } from 'react'

import {
  INITIAL_SCANNER_STATE,
  scannerReducer,
  type CaptureMode,
  type ScannerPhase,
} from './captureLoop'
import { DEFAULT_QUALITY_GATE_CONFIG, evaluateQualityGate, type AutoCaptureDecision } from './qualityGate'
import { advanceStability, INITIAL_STABILITY, type StabilityState } from './stability'
import { DEFAULT_SCANNER_CONFIG, type ScannerConfig } from './scannerConfig'
import type { FrameAnalysis } from './types'

interface Options {
  analysis: FrameAnalysis | null
  enabled: boolean
  sourceWidth: number
  sourceHeight: number
  onAutoCapture: () => boolean | Promise<boolean>
  config?: ScannerConfig
}

export interface AutoCaptureController {
  mode: CaptureMode
  phase: ScannerPhase
  decision: AutoCaptureDecision
  setMode: (mode: CaptureMode) => void
  markManualCaptureStarted: () => void
  notifyCaptureFinished: () => void
  reset: () => void
}

const INITIAL_DECISION: AutoCaptureDecision = { ready: false, reason: 'no_document' }

function qualityFromAnalysis(analysis: FrameAnalysis, sourceWidth: number, sourceHeight: number) {
  const values = [
    analysis.sharpness,
    analysis.meanLuminance,
    analysis.darkPixelRatio,
    analysis.brightPixelRatio,
    analysis.areaRatio,
    analysis.detectionConfidence,
    analysis.perspectiveScore,
  ]
  if (!analysis.corners || analysis.corners.length !== 4 || values.some((value) => !Number.isFinite(value))
    || sourceWidth <= 0 || sourceHeight <= 0
    || analysis.corners.some(({ x, y }) => !Number.isFinite(x) || !Number.isFinite(y)
      || x < 0 || x > sourceWidth || y < 0 || y > sourceHeight)) return null
  return {
    sharpness: analysis.sharpness,
    meanLuminance: analysis.meanLuminance!,
    darkPixelRatio: analysis.darkPixelRatio!,
    brightPixelRatio: analysis.brightPixelRatio!,
    areaRatio: analysis.areaRatio!,
    detectionConfidence: analysis.detectionConfidence!,
    clipped: analysis.clipped ?? true,
    perspectiveScore: analysis.perspectiveScore!,
  }
}

export function useAutoCapture({
  analysis,
  enabled,
  sourceWidth,
  sourceHeight,
  onAutoCapture,
  config = DEFAULT_SCANNER_CONFIG,
}: Options): AutoCaptureController {
  const [scanner, dispatch] = useReducer(scannerReducer, INITIAL_SCANNER_STATE)
  const [decision, setDecision] = useState<AutoCaptureDecision>(INITIAL_DECISION)
  const stabilityRef = useRef<StabilityState>(INITIAL_STABILITY)
  const onAutoCaptureRef = useRef(onAutoCapture)
  onAutoCaptureRef.current = onAutoCapture

  useEffect(() => {
    if (!enabled) {
      stabilityRef.current = INITIAL_STABILITY
      setDecision(INITIAL_DECISION)
      dispatch({ type: 'retake' })
      return
    }
    if (!analysis) {
      stabilityRef.current = INITIAL_STABILITY
      setDecision(INITIAL_DECISION)
      dispatch({ type: 'quality_evaluated', ready: false, stableLongEnough: false })
      return
    }

    const quality = qualityFromAnalysis(analysis, sourceWidth, sourceHeight)
    if (!quality) {
      stabilityRef.current = INITIAL_STABILITY
      setDecision(INITIAL_DECISION)
      dispatch({ type: 'quality_evaluated', ready: false, stableLongEnough: false })
      return
    }

    const now = performance.now()
    const stability = advanceStability(
      stabilityRef.current,
      { corners: analysis.corners, areaRatio: quality.areaRatio },
      now,
      sourceWidth,
      sourceHeight,
      config,
    )
    stabilityRef.current = stability.state
    const nextDecision = evaluateQualityGate({
      ...quality,
      stabilityScore: stability.stableLongEnough ? 1 : 0,
      stableLongEnough: stability.stableLongEnough,
    }, {
      ...DEFAULT_QUALITY_GATE_CONFIG,
      minAreaRatio: config.autoMinAreaRatio,
      minDetectionConfidence: config.autoMinDetectionConfidence,
      maxPerspectiveRatio: config.maxPerspectiveRatio,
      minSharpness: DEFAULT_QUALITY_GATE_CONFIG.minSharpness,
    })
    setDecision(nextDecision)
    dispatch({
      type: 'quality_evaluated',
      ready: nextDecision.ready,
      stableLongEnough: stability.stableLongEnough,
      at: now,
    })
  }, [analysis, config, enabled, sourceHeight, sourceWidth])

  useEffect(() => {
    if (!enabled || scanner.mode !== 'auto' || !scanner.autoArmed) return undefined
    const timer = window.setTimeout(() => {
      const result = onAutoCaptureRef.current()
      if (result instanceof Promise) {
        void result.then((started) => {
          if (!started) dispatch({ type: 'retake' })
        })
      } else if (!result) {
        dispatch({ type: 'retake' })
      }
    }, config.autoCaptureConfirmationMs)
    return () => window.clearTimeout(timer)
  }, [config.autoCaptureConfirmationMs, enabled, scanner.autoArmed, scanner.mode])

  const setMode = (mode: CaptureMode) => {
    stabilityRef.current = INITIAL_STABILITY
    setDecision(INITIAL_DECISION)
    dispatch({ type: 'mode_changed', mode })
  }

  const reset = () => {
    stabilityRef.current = INITIAL_STABILITY
    setDecision(INITIAL_DECISION)
    dispatch({ type: 'retake' })
  }

  return {
    mode: scanner.mode,
    phase: scanner.phase,
    decision,
    setMode,
    markManualCaptureStarted: () => dispatch({ type: 'capture_started' }),
    notifyCaptureFinished: reset,
    reset,
  }
}

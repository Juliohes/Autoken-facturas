import { DEFAULT_SCANNER_CONFIG } from './scannerConfig'
import type { CaptureQuality } from './types'

export type AutoCaptureReason =
  | 'no_document'
  | 'low_confidence'
  | 'too_small'
  | 'clipped'
  | 'blurry'
  | 'too_dark'
  | 'too_bright'
  | 'perspective_extreme'
  | 'moving'
  | 'ready'

export interface AutoCaptureDecision {
  ready: boolean
  reason: AutoCaptureReason
}

export interface QualityGateInput extends CaptureQuality {
  stableLongEnough: boolean
}

export interface QualityGateConfig {
  minAreaRatio: number
  minDetectionConfidence: number
  maxPerspectiveRatio: number
  minSharpness: number
  maxDarkPixelRatio: number
  maxBrightPixelRatio: number
  minLuminance: number
  maxLuminance: number
}

export const DEFAULT_QUALITY_GATE_CONFIG: QualityGateConfig = {
  minAreaRatio: DEFAULT_SCANNER_CONFIG.autoMinAreaRatio,
  minDetectionConfidence: DEFAULT_SCANNER_CONFIG.autoMinDetectionConfidence,
  maxPerspectiveRatio: DEFAULT_SCANNER_CONFIG.maxPerspectiveRatio,
  minSharpness: 100,
  maxDarkPixelRatio: 0.2,
  maxBrightPixelRatio: 0.2,
  minLuminance: 15,
  maxLuminance: 245,
}

export function evaluateQualityGate(
  quality: QualityGateInput,
  config: QualityGateConfig = DEFAULT_QUALITY_GATE_CONFIG,
): AutoCaptureDecision {
  if (!Number.isFinite(quality.detectionConfidence) || !Number.isFinite(quality.areaRatio)
    || quality.detectionConfidence <= 0 || quality.areaRatio <= 0) {
    return { ready: false, reason: 'no_document' }
  }
  if (quality.detectionConfidence < config.minDetectionConfidence) {
    return { ready: false, reason: 'low_confidence' }
  }
  if (quality.areaRatio < config.minAreaRatio) return { ready: false, reason: 'too_small' }
  if (quality.clipped) return { ready: false, reason: 'clipped' }
  if (!Number.isFinite(quality.sharpness) || quality.sharpness < config.minSharpness) {
    return { ready: false, reason: 'blurry' }
  }
  if (quality.meanLuminance < config.minLuminance || quality.darkPixelRatio > config.maxDarkPixelRatio) {
    return { ready: false, reason: 'too_dark' }
  }
  if (quality.meanLuminance > config.maxLuminance || quality.brightPixelRatio > config.maxBrightPixelRatio) {
    return { ready: false, reason: 'too_bright' }
  }
  if (!Number.isFinite(quality.perspectiveScore) || quality.perspectiveScore > config.maxPerspectiveRatio) {
    return { ready: false, reason: 'perspective_extreme' }
  }
  if (!quality.stableLongEnough || quality.stabilityScore < 1) return { ready: false, reason: 'moving' }
  return { ready: true, reason: 'ready' }
}

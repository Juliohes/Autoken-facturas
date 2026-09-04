export interface ScannerConfig {
  analysisIntervalMs: number
  previewLongEdgePx: number
  stillAnalysisLongEdgePx: number
  detectionMinAreaRatio: number
  autoMinAreaRatio: number
  autoMinDetectionConfidence: number
  minFrameMarginRatio: number
  maxPerspectiveRatio: number
  stableRequiredMs: number
  stableMinFrames: number
  maxCornerMovementRatio: number
  maxAreaVariationRatio: number
  autoCaptureConfirmationMs: number
}

export const DEFAULT_SCANNER_CONFIG: ScannerConfig = {
  analysisIntervalMs: 200,
  previewLongEdgePx: 720,
  stillAnalysisLongEdgePx: 1600,
  detectionMinAreaRatio: 0.15,
  autoMinAreaRatio: 0.3,
  autoMinDetectionConfidence: 0.75,
  minFrameMarginRatio: 0.02,
  maxPerspectiveRatio: 2.2,
  stableRequiredMs: 700,
  stableMinFrames: 4,
  maxCornerMovementRatio: 0.012,
  maxAreaVariationRatio: 0.04,
  autoCaptureConfirmationMs: 350,
}

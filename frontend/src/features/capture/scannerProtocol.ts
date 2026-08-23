import type { FrameAnalysis, NormalizedCorners } from './types'
export type { NormalizedCorners, NormalizedPoint } from './types'

export type ScannerPreviewImage = ImageBitmap | ImageData

export type ScannerWorkerRequest =
  | { type: 'INIT'; requestId: number }
  | {
      type: 'ANALYZE_PREVIEW'
      requestId: number
      image: ScannerPreviewImage
      sourceWidth: number
      sourceHeight: number
    }
  | { type: 'ANALYZE_STILL'; requestId: number; image: ImageBitmap }
  | {
      type: 'PROCESS_FINAL'
      requestId: number
      image: ImageBitmap
      corners: NormalizedCorners | null
      filter: 'natural'
    }

export type ScannerWorkerResponse =
  | { type: 'READY'; requestId: number }
  | { type: 'PREVIEW_ANALYSIS'; requestId: number; analysis: FrameAnalysis }
  | { type: 'STILL_ANALYSIS'; requestId: number; analysis: FrameAnalysis }
  | { type: 'PROCESSED_FINAL'; requestId: number; blob: Blob }
  | { type: 'ERROR'; requestId: number; code: string }

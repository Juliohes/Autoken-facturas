import { describe, expect, it, vi } from 'vitest'

import { createScannerCoordinator } from './useScannerEngine'
import type { ScannerWorkerResponse } from './scannerProtocol'
import type { FrameAnalysis } from './types'

const ANALYSIS: FrameAnalysis = { sharpness: 180, corners: null }

function response(message: ScannerWorkerResponse): ScannerWorkerResponse {
  return message
}

describe('scanner coordinator', () => {
  it('mantiene un solo análisis en vuelo, descarta frames ocupados e ignora resultados obsoletos', () => {
    const worker = { postMessage: vi.fn(), terminate: vi.fn() }
    const onAnalysis = vi.fn()
    const coordinator = createScannerCoordinator(worker, onAnalysis)

    expect(worker.postMessage).toHaveBeenCalledWith({ type: 'INIT', requestId: 0 })
    expect(coordinator.submitPreview({} as ImageBitmap, 640, 480)).toBe(false)
    coordinator.handleMessage(response({ type: 'READY', requestId: 0 }))

    const firstFrame = {} as ImageBitmap
    const secondFrame = {} as ImageBitmap
    expect(coordinator.submitPreview(firstFrame, 640, 480)).toBe(true)
    expect(coordinator.submitPreview(secondFrame, 640, 480)).toBe(false)
    expect(worker.postMessage).toHaveBeenCalledTimes(2)

    coordinator.handleMessage(response({ type: 'PREVIEW_ANALYSIS', requestId: 1, analysis: ANALYSIS }))
    expect(onAnalysis).toHaveBeenCalledWith(ANALYSIS)

    expect(coordinator.submitPreview(secondFrame, 640, 480)).toBe(true)
    coordinator.handleMessage(response({ type: 'PREVIEW_ANALYSIS', requestId: 1, analysis: ANALYSIS }))
    expect(onAnalysis).toHaveBeenCalledTimes(1)

    coordinator.handleMessage(response({ type: 'PREVIEW_ANALYSIS', requestId: 2, analysis: ANALYSIS }))
    expect(onAnalysis).toHaveBeenCalledTimes(2)
  })
})

import { useEffect, useRef, useState } from 'react'

import type { ScannerPreviewImage, ScannerWorkerResponse } from './scannerProtocol'
import { DEFAULT_SCANNER_CONFIG } from './scannerConfig'
import type { FrameAnalysis } from './types'

interface ScannerWorkerLike {
  postMessage: Worker['postMessage']
  terminate: () => void
  onmessage?: ((event: MessageEvent<ScannerWorkerResponse>) => void) | null
  onerror?: ((event: ErrorEvent) => void) | null
}

interface ScannerCoordinator {
  canSubmitPreview: () => boolean
  handleMessage: (message: ScannerWorkerResponse) => void
  submitPreview: (image: ScannerPreviewImage, sourceWidth: number, sourceHeight: number) => boolean
  dispose: () => void
}

export function createScannerCoordinator(
  worker: ScannerWorkerLike,
  onAnalysis: (analysis: FrameAnalysis) => void,
  onError: () => void = () => undefined,
): ScannerCoordinator {
  let nextRequestId = 1
  let latestRequestId = 0
  let inFlightRequestId: number | null = null
  let ready = false
  let disposed = false

  worker.postMessage({ type: 'INIT', requestId: 0 })

  return {
    handleMessage(message) {
      if (disposed || message.requestId < latestRequestId) return
      if (message.type === 'READY') {
        ready = true
        return
      }
      if (message.type === 'ERROR') {
        if (message.requestId === inFlightRequestId) {
          inFlightRequestId = null
          onError()
        }
        return
      }
      if (message.type !== 'PREVIEW_ANALYSIS' || message.requestId !== inFlightRequestId) return
      inFlightRequestId = null
      onAnalysis(message.analysis)
    },
    canSubmitPreview() {
      return !disposed && ready && inFlightRequestId === null
    },
  submitPreview(image, sourceWidth, sourceHeight) {
      if (!this.canSubmitPreview()) return false
      const requestId = nextRequestId++
      latestRequestId = requestId
      inFlightRequestId = requestId
      worker.postMessage(
        { type: 'ANALYZE_PREVIEW', requestId, image, sourceWidth, sourceHeight },
        'close' in image ? [image] : [],
      )
      return true
    },
    dispose() {
      disposed = true
      inFlightRequestId = null
      worker.onmessage = undefined
      worker.onerror = undefined
      worker.terminate()
    },
  }
}

export interface ScannerEngineOptions {
  enabled?: boolean
  intervalMs?: number
}

export interface ScannerEngineState {
  analysis: FrameAnalysis | null
  error: boolean
}

function capturePreview(video: HTMLVideoElement): Promise<ScannerPreviewImage> {
  const longEdge = Math.max(video.videoWidth, video.videoHeight)
  const scale = longEdge > DEFAULT_SCANNER_CONFIG.previewLongEdgePx
    ? DEFAULT_SCANNER_CONFIG.previewLongEdgePx / longEdge
    : 1
  const width = Math.max(1, Math.round(video.videoWidth * scale))
  const height = Math.max(1, Math.round(video.videoHeight * scale))

  if (typeof createImageBitmap === 'function') {
    return createImageBitmap(video, { resizeWidth: width, resizeHeight: height, resizeQuality: 'medium' })
  }

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) return Promise.reject(new Error('canvas-unavailable'))
  context.drawImage(video, 0, 0, width, height)
  if (typeof createImageBitmap === 'function') return createImageBitmap(canvas)
  return Promise.resolve(context.getImageData(0, 0, width, height))
}

function closePreview(image: ScannerPreviewImage) {
  if ('close' in image) image.close()
}

export function useScannerEngine(
  video: HTMLVideoElement | null,
  options: ScannerEngineOptions = {},
): ScannerEngineState {
  const { enabled = true, intervalMs = DEFAULT_SCANNER_CONFIG.analysisIntervalMs } = options
  const [state, setState] = useState<ScannerEngineState>({ analysis: null, error: false })
  const coordinatorRef = useRef<ScannerCoordinator | null>(null)

  useEffect(() => {
    // Sin OffscreenCanvas no se inicia un worker que fallaría al convertir el frame; el botón
    // MANUAL sigue disponible como degradación segura para navegadores antiguos.
    if (!enabled || !video || typeof Worker === 'undefined' || typeof OffscreenCanvas === 'undefined') {
      coordinatorRef.current?.dispose()
      coordinatorRef.current = null
      setState({ analysis: null, error: false })
      return undefined
    }

    let worker: Worker
    try {
      worker = new Worker(new URL('./scanner.worker.ts', import.meta.url), { type: 'module' })
    } catch {
      setState({ analysis: null, error: true })
      return undefined
    }
    const coordinator = createScannerCoordinator(
      worker,
      (analysis) => setState((current) => ({ ...current, analysis })),
      () => setState((current) => ({ ...current, error: true })),
    )
    coordinatorRef.current = coordinator
    worker.onmessage = (event) => coordinator.handleMessage(event.data)
    worker.onerror = () => setState((current) => ({ ...current, error: true }))

    let cancelled = false
    let timeout: number | undefined
    let videoFrameCallback: number | undefined
    let nextAllowedAt = 0
    let pendingPreview: { image: ScannerPreviewImage; sourceWidth: number; sourceHeight: number } | null = null
    const requestVideoFrame = (video as HTMLVideoElement & {
      requestVideoFrameCallback?: (callback: () => void) => number
    }).requestVideoFrameCallback

    const schedule = () => {
      if (cancelled) return
      if (requestVideoFrame) videoFrameCallback = requestVideoFrame.call(video, tick)
      else timeout = window.setTimeout(tick, intervalMs)
    }
    const submitPendingPreview = () => {
      if (!pendingPreview || !coordinator.canSubmitPreview()) return
      const preview = pendingPreview
      pendingPreview = null
      if (!coordinator.submitPreview(preview.image, preview.sourceWidth, preview.sourceHeight)) closePreview(preview.image)
    }

    const tick = () => {
      if (cancelled) return
      submitPendingPreview()
      const now = performance.now()
      if (now >= nextAllowedAt && video.videoWidth > 0 && video.videoHeight > 0) {
        nextAllowedAt = now + intervalMs
        void capturePreview(video).then((image) => {
          if (cancelled) {
            closePreview(image)
            return
          }
          if (pendingPreview) closePreview(pendingPreview.image)
          pendingPreview = { image, sourceWidth: video.videoWidth, sourceHeight: video.videoHeight }
          submitPendingPreview()
        }).catch(() => undefined)
      }
      schedule()
    }

    schedule()
    return () => {
      cancelled = true
      if (timeout !== undefined) window.clearTimeout(timeout)
      if (videoFrameCallback !== undefined) {
        const cancel = (video as HTMLVideoElement & { cancelVideoFrameCallback?: (handle: number) => void }).cancelVideoFrameCallback
        cancel?.call(video, videoFrameCallback)
      }
      if (pendingPreview) closePreview(pendingPreview.image)
      pendingPreview = null
      if (coordinatorRef.current === coordinator) coordinatorRef.current = null
      coordinator.dispose()
    }
  }, [enabled, intervalMs, video])

  return state
}

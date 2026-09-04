import { analyzeFrame } from './analyzeFrame'
import { warpToCorners } from './opencv/documentEdges'
import { loadOpenCv } from './opencv/loadOpenCv'
import type { ScannerPreviewImage, ScannerWorkerRequest, ScannerWorkerResponse } from './scannerProtocol'
import type { Corner } from './types'

const workerScope = globalThis as unknown as {
  onmessage: ((event: MessageEvent<ScannerWorkerRequest>) => void) | null
  postMessage: (message: ScannerWorkerResponse, transfer?: Transferable[]) => void
}

async function imageToImageData(image: ScannerPreviewImage): Promise<ImageData> {
  if ('data' in image) return image
  const canvas = new OffscreenCanvas(image.width, image.height)
  const context = canvas.getContext('2d')
  if (!context) throw new Error('canvas-unavailable')
  context.drawImage(image, 0, 0)
  return context.getImageData(0, 0, image.width, image.height)
}

function normalizedCornersToPixels(
  corners: NonNullable<Extract<ScannerWorkerRequest, { type: 'PROCESS_FINAL' }>['corners']>,
  width: number,
  height: number,
): Corner[] {
  return corners.map(({ x, y }) => ({ x: x * width, y: y * height }))
}

async function imageDataToJpeg(imageData: ImageData): Promise<Blob> {
  const canvas = new OffscreenCanvas(imageData.width, imageData.height)
  const context = canvas.getContext('2d')
  if (!context) throw new Error('canvas-unavailable')
  context.putImageData(imageData, 0, 0)
  return canvas.convertToBlob({ type: 'image/jpeg', quality: 0.85 })
}

function normalizePreviewAnalysis(analysis: Awaited<ReturnType<typeof analyzeFrame>>, imageData: ImageData, sourceWidth: number, sourceHeight: number) {
  if (!analysis.corners || imageData.width <= 0 || imageData.height <= 0) return analysis
  return {
    ...analysis,
    corners: analysis.corners.map(({ x, y }) => ({
      x: x * sourceWidth / imageData.width,
      y: y * sourceHeight / imageData.height,
    })),
  }
}

async function handleRequest(request: ScannerWorkerRequest) {
  if (request.type === 'INIT') {
    workerScope.postMessage({ type: 'READY', requestId: request.requestId })
    return
  }

  try {
    const imageData = await imageToImageData(request.image)
    if ('close' in request.image) request.image.close()

    if (request.type === 'ANALYZE_PREVIEW') {
      const analysis = normalizePreviewAnalysis(
        await analyzeFrame(imageData),
        imageData,
        request.sourceWidth,
        request.sourceHeight,
      )
      workerScope.postMessage({ type: 'PREVIEW_ANALYSIS', requestId: request.requestId, analysis })
      return
    }

    if (request.type === 'ANALYZE_STILL') {
      const analysis = await analyzeFrame(imageData)
      workerScope.postMessage({ type: 'STILL_ANALYSIS', requestId: request.requestId, analysis })
      return
    }

    const output = request.corners
      ? warpToCorners(
          await loadOpenCv(),
          imageData,
          normalizedCornersToPixels(request.corners, imageData.width, imageData.height),
        )
      : imageData
    const blob = await imageDataToJpeg(output)
    workerScope.postMessage({ type: 'PROCESSED_FINAL', requestId: request.requestId, blob })
  } catch (error) {
    workerScope.postMessage({
      type: 'ERROR',
      requestId: request.requestId,
      code: error instanceof Error ? error.message : 'scanner-error',
    })
  }
}

workerScope.onmessage = (event) => {
  void handleRequest(event.data)
}

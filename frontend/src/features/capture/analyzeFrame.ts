// Análisis de un frame ya capturado (S2.2): nitidez + esquinas de documento. Compartido entre el
// captura manual (`CaptureScreen`), para no repetir la carga de OpenCV.js ni la orquestación
// blur+bordes.
import { computeBlurScore } from './opencv/blur'
import { detectDocument } from './opencv/documentEdges'
import { loadOpenCv } from './opencv/loadOpenCv'
import { inspectFrameQuality } from './qualitySignals'
import { DEFAULT_SCANNER_CONFIG, type ScannerConfig } from './scannerConfig'
import type { FrameAnalysis } from './types'

export function analysisDimensions(
  sourceWidth: number,
  sourceHeight: number,
  longEdge = DEFAULT_SCANNER_CONFIG.stillAnalysisLongEdgePx,
) {
  const sourceLongEdge = Math.max(sourceWidth, sourceHeight)
  if (sourceLongEdge <= longEdge) return { width: sourceWidth, height: sourceHeight }
  const scale = longEdge / sourceLongEdge
  return { width: Math.max(1, Math.round(sourceWidth * scale)), height: Math.max(1, Math.round(sourceHeight * scale)) }
}

function createCanvas(width: number, height: number): HTMLCanvasElement | OffscreenCanvas | null {
  if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(width, height)
  if (typeof document === 'undefined') return null
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  return canvas
}

function resizeForAnalysis(frame: ImageData, config: ScannerConfig): ImageData {
  const dimensions = analysisDimensions(frame.width, frame.height, config.stillAnalysisLongEdgePx)
  if (dimensions.width === frame.width && dimensions.height === frame.height) return frame
  const sourceCanvas = createCanvas(frame.width, frame.height)
  const sourceContext = sourceCanvas?.getContext('2d') as CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D | null
  if (!sourceCanvas || !sourceContext) return frame
  sourceContext.putImageData(frame, 0, 0)
  const targetCanvas = createCanvas(dimensions.width, dimensions.height)
  const targetContext = targetCanvas?.getContext('2d') as CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D | null
  if (!targetContext) return frame
  targetContext.drawImage(sourceCanvas, 0, 0, dimensions.width, dimensions.height)
  return targetContext.getImageData(0, 0, dimensions.width, dimensions.height)
}

function scaleCornersToSource(corners: NonNullable<FrameAnalysis['corners']>, analysis: ImageData, source: ImageData) {
  if (analysis.width === source.width && analysis.height === source.height) return corners
  return corners.map(({ x, y }) => ({ x: x * source.width / analysis.width, y: y * source.height / analysis.height }))
}

function documentRoi(frame: ImageData, corners: FrameAnalysis['corners']): ImageData {
  if (!corners || corners.length !== 4) return frame
  const left = Math.max(0, Math.floor(Math.min(...corners.map(({ x }) => x))))
  const top = Math.max(0, Math.floor(Math.min(...corners.map(({ y }) => y))))
  const right = Math.min(frame.width, Math.ceil(Math.max(...corners.map(({ x }) => x))))
  const bottom = Math.min(frame.height, Math.ceil(Math.max(...corners.map(({ y }) => y))))
  const width = right - left
  const height = bottom - top
  if (width <= 0 || height <= 0) return frame

  const data = new Uint8ClampedArray(width * height * 4)
  for (let row = 0; row < height; row += 1) {
    const sourceStart = ((top + row) * frame.width + left) * 4
    data.set(frame.data.subarray(sourceStart, sourceStart + width * 4), row * width * 4)
  }
  return new ImageData(data, width, height)
}

export async function analyzeFrame(
  frame: ImageData,
  config: ScannerConfig = DEFAULT_SCANNER_CONFIG,
): Promise<FrameAnalysis> {
  const cv = await loadOpenCv()
  const analysisFrame = resizeForAnalysis(frame, config)
  const detection = detectDocument(cv, analysisFrame, config)
  const quality = inspectFrameQuality(analysisFrame, detection.corners, config.minFrameMarginRatio)
  return {
    // La nitidez se calcula sobre la zona del documento, no sobre la mesa o el fondo.
    sharpness: computeBlurScore(cv, documentRoi(analysisFrame, detection.corners)),
    corners: detection.corners ? scaleCornersToSource(detection.corners, analysisFrame, frame) : null,
    detectionConfidence: detection.confidence,
    areaRatio: detection.areaRatio,
    detectionMethod: detection.method,
    ...quality,
  }
}

// Análisis de un frame ya capturado (S2.2): nitidez + esquinas de documento. Compartido entre el
// captura manual (`CaptureScreen`), para no repetir la carga de OpenCV.js ni la orquestación
// blur+bordes.
import { computeBlurScore } from './opencv/blur'
import { detectDocument } from './opencv/documentEdges'
import { loadOpenCv } from './opencv/loadOpenCv'
import type { FrameAnalysis } from './types'

const STILL_ANALYSIS_LONG_EDGE_PX = 1600

export function analysisDimensions(sourceWidth: number, sourceHeight: number, longEdge = STILL_ANALYSIS_LONG_EDGE_PX) {
  const sourceLongEdge = Math.max(sourceWidth, sourceHeight)
  if (sourceLongEdge <= longEdge) return { width: sourceWidth, height: sourceHeight }
  const scale = longEdge / sourceLongEdge
  return { width: Math.max(1, Math.round(sourceWidth * scale)), height: Math.max(1, Math.round(sourceHeight * scale)) }
}

function resizeForAnalysis(frame: ImageData): ImageData {
  const dimensions = analysisDimensions(frame.width, frame.height)
  if (dimensions.width === frame.width && dimensions.height === frame.height) return frame
  const sourceCanvas = document.createElement('canvas')
  sourceCanvas.width = frame.width
  sourceCanvas.height = frame.height
  const sourceContext = sourceCanvas.getContext('2d')
  if (!sourceContext) return frame
  sourceContext.putImageData(frame, 0, 0)
  const targetCanvas = document.createElement('canvas')
  targetCanvas.width = dimensions.width
  targetCanvas.height = dimensions.height
  const targetContext = targetCanvas.getContext('2d')
  if (!targetContext) return frame
  targetContext.drawImage(sourceCanvas, 0, 0, dimensions.width, dimensions.height)
  return targetContext.getImageData(0, 0, dimensions.width, dimensions.height)
}

function scaleCornersToSource(corners: NonNullable<FrameAnalysis['corners']>, analysis: ImageData, source: ImageData) {
  if (analysis.width === source.width && analysis.height === source.height) return corners
  return corners.map(({ x, y }) => ({ x: x * source.width / analysis.width, y: y * source.height / analysis.height }))
}

export async function analyzeFrame(frame: ImageData): Promise<FrameAnalysis> {
  const cv = await loadOpenCv()
  const analysisFrame = resizeForAnalysis(frame)
  const detection = detectDocument(cv, analysisFrame)
  return {
    sharpness: computeBlurScore(cv, analysisFrame),
    corners: detection.corners ? scaleCornersToSource(detection.corners, analysisFrame, frame) : null,
    detectionConfidence: detection.confidence,
    areaRatio: detection.areaRatio,
    detectionMethod: detection.method,
  }
}

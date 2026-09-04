// Post-procesado de una captura ya hecha (S2.2 decisiones 6/8): si hay esquinas, recorta y endereza
// antes de normalizar a JPEG; si no, normaliza el frame completo tal cual (C8/C9, nunca bloquea por
// no encontrar bordes). Aparte de `CaptureScreen` para poder mockearlo entero en sus tests (jsdom no
// reproduce vídeo/canvas real).
import { warpToCorners } from './opencv/documentEdges'
import { loadOpenCv } from './opencv/loadOpenCv'
import { imageDataToJpegBlob } from './normalizeToJpeg'
import { DEFAULT_SCANNER_CONFIG, type ScannerConfig } from './scannerConfig'
import type { Corner } from './types'

function edgeLength(first: Corner, second: Corner): number {
  return Math.hypot(first.x - second.x, first.y - second.y)
}

function polygonArea(corners: Corner[]): number {
  return Math.abs(corners.reduce((area, corner, index) => {
    const next = corners[(index + 1) % corners.length]
    return area + corner.x * next.y - next.x * corner.y
  }, 0)) / 2
}

function perspectiveRatio(corners: Corner[]): number {
  const [topLeft, topRight, bottomRight, bottomLeft] = corners
  const horizontal = [edgeLength(topLeft, topRight), edgeLength(bottomLeft, bottomRight)]
  const vertical = [edgeLength(topLeft, bottomLeft), edgeLength(topRight, bottomRight)]
  const ratios = [horizontal, vertical].map(([first, second]) => {
    if (Math.min(first, second) <= 0) return Number.POSITIVE_INFINITY
    return Math.max(first, second) / Math.min(first, second)
  })
  return Math.max(...ratios)
}

export function isReliableDocumentGeometry(
  frame: Pick<ImageData, 'width' | 'height'>,
  corners: Corner[] | null,
  config: ScannerConfig = DEFAULT_SCANNER_CONFIG,
): boolean {
  if (!corners || corners.length !== 4 || frame.width <= 0 || frame.height <= 0) return false
  if (corners.some(({ x, y }) => !Number.isFinite(x) || !Number.isFinite(y)
    || x < 0 || x > frame.width || y < 0 || y > frame.height)) return false
  const margin = Math.min(frame.width, frame.height) * config.minFrameMarginRatio
  if (corners.some(({ x, y }) => Math.min(x, frame.width - x, y, frame.height - y) < margin)) return false
  if (polygonArea(corners) / (frame.width * frame.height) < config.detectionMinAreaRatio) return false
  return perspectiveRatio(corners) <= config.maxPerspectiveRatio
}

export async function processCapturedFrame(frame: ImageData, corners: Corner[] | null): Promise<Blob> {
  if (!isReliableDocumentGeometry(frame, corners) || !corners) return imageDataToJpegBlob(frame)
  try {
    const cv = await loadOpenCv()
    const warped = warpToCorners(cv, frame, corners)
    return await imageDataToJpegBlob(warped)
  } catch {
    // El recorte es una mejora, no una condición para conservar la captura.
    return imageDataToJpegBlob(frame)
  }
}

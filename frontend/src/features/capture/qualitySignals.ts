import type { Corner } from './types'
import { DEFAULT_SCANNER_CONFIG } from './scannerConfig'

export interface FrameQualitySignals {
  meanLuminance: number
  darkPixelRatio: number
  brightPixelRatio: number
  clipped: boolean
  perspectiveScore: number
}

const DARK_LUMINANCE = 15
const BRIGHT_LUMINANCE = 245

function luminance(red: number, green: number, blue: number): number {
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue
}

function edgeRatio(first: Corner, second: Corner, third: Corner, fourth: Corner): number {
  const firstLength = Math.hypot(first.x - second.x, first.y - second.y)
  const secondLength = Math.hypot(third.x - fourth.x, third.y - fourth.y)
  if (Math.min(firstLength, secondLength) <= 0) return Number.POSITIVE_INFINITY
  return Math.max(firstLength, secondLength) / Math.min(firstLength, secondLength)
}

function perspectiveScore(corners: Corner[] | null): number {
  if (!corners || corners.length !== 4) return Number.POSITIVE_INFINITY
  const [topLeft, topRight, bottomRight, bottomLeft] = corners
  return Math.max(
    edgeRatio(topLeft, topRight, bottomRight, bottomLeft),
    edgeRatio(topLeft, bottomLeft, topRight, bottomRight),
  )
}

function isClipped(corners: Corner[] | null, width: number, height: number, marginRatio: number): boolean {
  if (!corners || corners.length !== 4 || width <= 0 || height <= 0) return true
  const margin = Math.min(width, height) * marginRatio
  return corners.some(({ x, y }) => Math.min(x, width - x, y, height - y) < margin)
}

export function inspectFrameQuality(
  image: ImageData,
  corners: Corner[] | null,
  clippingMarginRatio = DEFAULT_SCANNER_CONFIG.minFrameMarginRatio,
): FrameQualitySignals {
  const pixelCount = image.width * image.height
  let totalLuminance = 0
  let darkPixels = 0
  let brightPixels = 0

  for (let index = 0; index < image.data.length; index += 4) {
    const value = luminance(image.data[index], image.data[index + 1], image.data[index + 2])
    totalLuminance += value
    if (value < DARK_LUMINANCE) darkPixels += 1
    if (value > BRIGHT_LUMINANCE) brightPixels += 1
  }

  return {
    meanLuminance: pixelCount > 0 ? totalLuminance / pixelCount : 0,
    darkPixelRatio: pixelCount > 0 ? darkPixels / pixelCount : 1,
    brightPixelRatio: pixelCount > 0 ? brightPixels / pixelCount : 1,
    clipped: isClipped(corners, image.width, image.height, clippingMarginRatio),
    perspectiveScore: perspectiveScore(corners),
  }
}

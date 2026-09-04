import { describe, expect, it } from 'vitest'

import { inspectFrameQuality } from './qualitySignals'

function imageData(pixels: number[][]): ImageData {
  const height = pixels.length
  const width = pixels[0].length
  const data = new Uint8ClampedArray(width * height * 4)
  pixels.flat().forEach((luminance, index) => {
    data[index * 4] = luminance
    data[index * 4 + 1] = luminance
    data[index * 4 + 2] = luminance
    data[index * 4 + 3] = 255
  })
  return new ImageData(data, width, height)
}

describe('inspectFrameQuality', () => {
  it('calcula luminancia media y proporciones de píxeles extremos', () => {
    const result = inspectFrameQuality(imageData([[0, 15], [245, 255]]), [
      { x: 0.5, y: 0.5 },
      { x: 1.5, y: 0.5 },
      { x: 1.5, y: 1.5 },
      { x: 0.5, y: 1.5 },
    ])

    expect(result.meanLuminance).toBe(128.75)
    expect(result.darkPixelRatio).toBe(0.25)
    expect(result.brightPixelRatio).toBe(0.25)
  })

  it('marca esquinas dentro de la banda del borde y calcula la perspectiva', () => {
    const result = inspectFrameQuality(imageData([[128, 128, 128, 128], [128, 128, 128, 128], [128, 128, 128, 128], [128, 128, 128, 128]]), [
      { x: 0.1, y: 0.5 },
      { x: 3.5, y: 0.5 },
      { x: 3.5, y: 3.5 },
      { x: 0.1, y: 3.5 },
    ])

    expect(result.clipped).toBe(false)
    expect(result.perspectiveScore).toBe(1)

    expect(inspectFrameQuality(imageData([[128, 128, 128, 128], [128, 128, 128, 128], [128, 128, 128, 128], [128, 128, 128, 128]]), [
      { x: 0, y: 0 },
      { x: 2, y: 0.5 },
      { x: 3.5, y: 3.5 },
      { x: 0, y: 3.5 },
    ]).clipped).toBe(true)
  })
})

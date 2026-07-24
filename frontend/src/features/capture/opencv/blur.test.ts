// OpenCV.js real (WASM), no mockeado (S2.2 decisión 10) — confirma que el umbral de nitidez
// distingue de verdad una imagen nítida de una borrosa, no solo que la función no lanza.
import { describe, expect, it } from 'vitest'

import { loadOpenCvForTests } from '../test/loadOpenCvForTests'
import { makeDocumentImageData, makeNoDocumentImageData } from '../test/fixtures'
import { computeBlurScore } from './blur'
import type { CvModule } from './cvTypes'

function blurImage(cv: CvModule, imageData: ImageData): ImageData {
  const src = cv.matFromImageData(imageData)
  const dst = new cv.Mat()
  try {
    cv.GaussianBlur(src, dst, new cv.Size(25, 25), 0)
    return new ImageData(new Uint8ClampedArray(dst.data), dst.cols, dst.rows)
  } finally {
    src.delete()
    dst.delete()
  }
}

describe('computeBlurScore (OpenCV.js real)', () => {
  it('puntúa una imagen nítida (bordes marcados de un documento) más alto que su versión borrosa', async () => {
    const cv = await loadOpenCvForTests()
    const sharp = makeDocumentImageData()
    const blurred = blurImage(cv, sharp)

    const sharpScore = computeBlurScore(cv, sharp)
    const blurredScore = computeBlurScore(cv, blurred)

    expect(sharpScore).toBeGreaterThan(blurredScore)
  })

  it('una imagen plana de ruido uniforme sin bordes marcados puntúa bajo', async () => {
    const cv = await loadOpenCvForTests()
    const sharp = makeDocumentImageData()

    const noiseScore = computeBlurScore(cv, makeNoDocumentImageData())
    const sharpScore = computeBlurScore(cv, sharp)

    // El "ruido" aquí es un patrón determinista de bajo contraste (ver fixtures.ts), no bordes
    // reales de alto contraste como el rectángulo del documento — debe puntuar claramente más bajo.
    expect(noiseScore).toBeLessThan(sharpScore)
  })
})

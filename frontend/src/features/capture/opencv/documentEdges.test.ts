// OpenCV.js real (WASM), no mockeado (S2.2 decisión 10) — confirma que la detección de esquinas y
// el enderezado de perspectiva funcionan de verdad contra una imagen con un documento reconocible,
// y que "sin documento" da `null` en vez de un contorno inventado.
import { describe, expect, it } from 'vitest'

import { loadOpenCvForTests } from '../test/loadOpenCvForTests'
import { makeDocumentImageData, makeNoDocumentImageData, FIXTURE_HEIGHT, FIXTURE_WIDTH } from '../test/fixtures'
import { detectDocumentCorners, warpToCorners } from './documentEdges'

describe('detectDocumentCorners (OpenCV.js real)', () => {
  it('encuentra las 4 esquinas del documento en una imagen con bordes claros', async () => {
    const cv = await loadOpenCvForTests()
    const corners = detectDocumentCorners(cv, makeDocumentImageData())

    expect(corners).not.toBeNull()
    expect(corners).toHaveLength(4)
    // Orden canónico (sup-izq, sup-der, inf-der, inf-izq): la esquina 0 debe quedar arriba a la
    // izquierda (x e y menores que la esquina 2, inferior derecha).
    const [topLeft, , bottomRight] = corners as [
      { x: number; y: number },
      { x: number; y: number },
      { x: number; y: number },
      { x: number; y: number },
    ]
    expect(topLeft.x).toBeLessThan(bottomRight.x)
    expect(topLeft.y).toBeLessThan(bottomRight.y)
  })

  it('sin ningún documento reconocible, no inventa un contorno', async () => {
    const cv = await loadOpenCvForTests()
    const corners = detectDocumentCorners(cv, makeNoDocumentImageData())

    expect(corners).toBeNull()
  })
})

describe('warpToCorners (OpenCV.js real)', () => {
  it('endereza la región de las esquinas a un rectángulo del tamaño esperado', async () => {
    const cv = await loadOpenCvForTests()
    const source = makeDocumentImageData()
    const corners = detectDocumentCorners(cv, source)
    expect(corners).not.toBeNull()

    const warped = warpToCorners(cv, source, corners as NonNullable<typeof corners>)

    // El documento sintético mide (WIDTH - 2*margen) x (HEIGHT - 2*margen); el enderezado debe
    // acercarse a ese tamaño, no quedarse en el tamaño del frame completo original.
    expect(warped.width).toBeLessThan(FIXTURE_WIDTH)
    expect(warped.height).toBeLessThan(FIXTURE_HEIGHT)
    expect(warped.width).toBeGreaterThan(FIXTURE_WIDTH * 0.5)
    expect(warped.height).toBeGreaterThan(FIXTURE_HEIGHT * 0.5)
  })
})

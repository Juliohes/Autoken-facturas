// OpenCV.js real (WASM), no mockeado (S2.2 decisión 10) — confirma que la detección de esquinas y
// el enderezado de perspectiva funcionan de verdad contra una imagen con un documento reconocible,
// y que "sin documento" da `null` en vez de un contorno inventado.
import { describe, expect, it } from 'vitest'

import { loadOpenCvForTests } from '../test/loadOpenCvForTests'
import {
  makeDocumentImageData,
  makeNoDocumentImageData,
  makeRoundedCornerDocumentImageData,
  makeUnevenLightingDocumentImageData,
} from '../test/fixtures'
import { detectDocumentCorners, warpToCorners, MIN_LONG_EDGE_PX } from './documentEdges'
import type { Corner } from '../types'

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

  // spec: docs/specs/S6.14-captura-alta-resolucion-y-confianza-nombre.md, C3
  it('S6.14 C3: con contraste desigual (dos zonas de brillo distinto), sigue detectando el documento', async () => {
    const cv = await loadOpenCvForTests()
    const corners = detectDocumentCorners(cv, makeUnevenLightingDocumentImageData())

    expect(corners).not.toBeNull()
    expect(corners).toHaveLength(4)
  })

  it('S6.14 C3: un contorno con 5-6 vértices (esquina achaflanada) recupera un rectángulo en vez de descartarse', async () => {
    const cv = await loadOpenCvForTests()
    const corners = detectDocumentCorners(cv, makeRoundedCornerDocumentImageData())

    expect(corners).not.toBeNull()
    expect(corners).toHaveLength(4)
  })
})

describe('warpToCorners (OpenCV.js real)', () => {
  it('endereza la región de las esquinas a un rectángulo del tamaño esperado', async () => {
    const cv = await loadOpenCvForTests()
    const source = makeDocumentImageData()
    const corners = detectDocumentCorners(cv, source)
    expect(corners).not.toBeNull()

    const warped = warpToCorners(cv, source, corners as NonNullable<typeof corners>)

    // El documento sintético (400x300, margen 40) mide 320x220: por debajo del suelo mínimo de
    // salida (S6.14 C2), así que sale escalado hacia ese suelo en vez de conservar su tamaño
    // original pequeño.
    expect(Math.max(warped.width, warped.height)).toBeGreaterThanOrEqual(MIN_LONG_EDGE_PX)
  })

  // spec: docs/specs/S6.14-captura-alta-resolucion-y-confianza-nombre.md, C2
  it('S6.14 C2: un rectángulo menor que el suelo mínimo se escala hacia arriba (interpolación cúbica)', async () => {
    const cv = await loadOpenCvForTests()
    const source = makeDocumentImageData()
    // Esquinas pequeñas explícitas (320x220), independientes de la detección real: documento
    // sintético 400x300 con margen 40.
    const smallCorners: Corner[] = [
      { x: 40, y: 40 },
      { x: 360, y: 40 },
      { x: 360, y: 260 },
      { x: 40, y: 260 },
    ]

    const warped = warpToCorners(cv, source, smallCorners)

    expect(Math.max(warped.width, warped.height)).toBeGreaterThanOrEqual(MIN_LONG_EDGE_PX)
    // El aspecto original (320x220) se conserva al escalar.
    expect(warped.width / warped.height).toBeCloseTo(320 / 220, 1)
  })

  it('S6.14 C2: un rectángulo ya mayor que el suelo mínimo no se toca (nunca se reduce)', async () => {
    const cv = await loadOpenCvForTests()
    // Imagen grande y sencilla (sin usar la detección real, que no hace falta para esta prueba de
    // escalado): un lienzo uniforme del tamaño necesario para contener las esquinas.
    const width = 3000
    const height = 2000
    const source = new ImageData(new Uint8ClampedArray(width * height * 4).fill(200), width, height)
    const largeCorners: Corner[] = [
      { x: 100, y: 100 },
      { x: 2600, y: 100 },
      { x: 2600, y: 1700 },
      { x: 100, y: 1700 },
    ]

    const warped = warpToCorners(cv, source, largeCorners)

    expect(warped.width).toBe(2500)
    expect(warped.height).toBe(1600)
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { imageDataToJpegBlob } from './normalizeToJpeg'
import { warpToCorners } from './opencv/documentEdges'
import { loadOpenCv } from './opencv/loadOpenCv'
import { isReliableDocumentGeometry, processCapturedFrame } from './processCapture'

vi.mock('./normalizeToJpeg', () => ({ imageDataToJpegBlob: vi.fn() }))
vi.mock('./opencv/documentEdges', () => ({ warpToCorners: vi.fn() }))
vi.mock('./opencv/loadOpenCv', () => ({ loadOpenCv: vi.fn() }))

const frame = { width: 1000, height: 800 }
const validCorners = [
  { x: 100, y: 80 },
  { x: 900, y: 80 },
  { x: 900, y: 720 },
  { x: 100, y: 720 },
]
const frameImage = new ImageData(new Uint8ClampedArray(frame.width * frame.height * 4), frame.width, frame.height)

describe('isReliableDocumentGeometry', () => {
  it('acepta un documento grande, dentro de la imagen y con perspectiva razonable', () => {
    expect(isReliableDocumentGeometry(frame, validCorners)).toBe(true)
  })

  it.each([
    ['esquinas no finitas', [{ x: Number.NaN, y: 80 }, ...validCorners.slice(1)]],
    ['esquinas fuera de la imagen', [{ x: -1, y: 80 }, ...validCorners.slice(1)]],
    ['documento recortado por el borde', [{ x: 1, y: 80 }, ...validCorners.slice(1)]],
    ['cuadrilátero degenerado', [{ x: 100, y: 80 }, { x: 100, y: 80 }, ...validCorners.slice(2)]],
    ['perspectiva extrema', [{ x: 100, y: 80 }, { x: 900, y: 80 }, { x: 900, y: 720 }, { x: 100, y: 100 }]],
  ])('rechaza %s y obliga a conservar la imagen completa', (_reason, corners) => {
    expect(isReliableDocumentGeometry(frame, corners)).toBe(false)
  })
})

describe('processCapturedFrame', () => {
  beforeEach(() => {
    vi.mocked(imageDataToJpegBlob).mockReset().mockResolvedValue(new Blob(['full']))
    vi.mocked(loadOpenCv).mockReset().mockResolvedValue({} as never)
    vi.mocked(warpToCorners).mockReset()
  })

  it('conserva la imagen completa si OpenCV falla al preparar el recorte', async () => {
    vi.mocked(loadOpenCv).mockRejectedValueOnce(new Error('opencv unavailable'))

    await processCapturedFrame(frameImage, validCorners)

    expect(imageDataToJpegBlob).toHaveBeenLastCalledWith(frameImage)
  })

  it('conserva la imagen completa si el warp falla aunque la geometría sea válida', async () => {
    vi.mocked(warpToCorners).mockImplementationOnce(() => {
      throw new Error('warp failed')
    })

    await processCapturedFrame(frameImage, validCorners)

    expect(imageDataToJpegBlob).toHaveBeenLastCalledWith(frameImage)
  })
})

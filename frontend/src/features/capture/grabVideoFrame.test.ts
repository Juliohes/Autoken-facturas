import { afterEach, describe, expect, it, vi } from 'vitest'

import { grabVideoFrame } from './grabVideoFrame'

const FRAME = new ImageData(new Uint8ClampedArray(4 * 4 * 4), 4, 4)

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  delete (window as unknown as { ImageCapture?: unknown }).ImageCapture
})

describe('grabVideoFrame (R-009)', () => {
  it('prefiere ImageCapture.takePhoto para conservar la resolución del still', async () => {
    const track = {} as MediaStreamTrack
    const photo = new Blob(['photo'], { type: 'image/jpeg' })
    const takePhoto = vi.fn().mockResolvedValue(photo)
    class FakeImageCapture {
      constructor(receivedTrack: MediaStreamTrack) {
        expect(receivedTrack).toBe(track)
      }

      takePhoto = takePhoto
    }
    Object.defineProperty(window, 'ImageCapture', { configurable: true, value: FakeImageCapture })
    const bitmap = { width: 4000, height: 3000, close: vi.fn() }
    vi.stubGlobal('createImageBitmap', vi.fn().mockResolvedValue(bitmap))
    const context = { drawImage: vi.fn(), getImageData: vi.fn().mockReturnValue(FRAME) }
    vi.spyOn(document, 'createElement').mockImplementation(() => ({
      width: 0,
      height: 0,
      getContext: () => context,
    } as unknown as HTMLCanvasElement))
    const video = {
      videoWidth: 1920,
      videoHeight: 1080,
      srcObject: { getVideoTracks: () => [track] },
    } as unknown as HTMLVideoElement

    await expect(grabVideoFrame(video)).resolves.toBe(FRAME)
    expect(takePhoto).toHaveBeenCalledOnce()
    expect(bitmap.close).toHaveBeenCalledOnce()
  })
})

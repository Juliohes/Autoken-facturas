// Captura el still HD con ImageCapture cuando el navegador lo ofrece. Safari/iOS y navegadores sin
// esa API conservan el fallback canvas, que es menos fiel pero universal.
interface ImageCaptureLike {
  takePhoto: () => Promise<Blob>
}

type ImageCaptureConstructor = new (track: MediaStreamTrack) => ImageCaptureLike

async function imageBlobToImageData(blob: Blob): Promise<ImageData> {
  if (typeof createImageBitmap !== 'function') throw new Error('bitmap-unavailable')
  const bitmap = await createImageBitmap(blob)
  const canvas = document.createElement('canvas')
  canvas.width = bitmap.width
  canvas.height = bitmap.height
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    bitmap.close()
    throw new Error('canvas-unavailable')
  }
  ctx.drawImage(bitmap, 0, 0)
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
  bitmap.close()
  return imageData
}

function canvasVideoFrame(video: HTMLVideoElement): ImageData | null {
  if (video.videoWidth === 0 || video.videoHeight === 0) return null
  const canvas = document.createElement('canvas')
  canvas.width = video.videoWidth
  canvas.height = video.videoHeight
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  ctx.drawImage(video, 0, 0)
  return ctx.getImageData(0, 0, canvas.width, canvas.height)
}

async function grabVideoFrameAsync(video: HTMLVideoElement): Promise<ImageData | null> {
  const stream = video.srcObject as MediaStream | null
  const track = stream?.getVideoTracks?.()[0]
  const ImageCapture = (window as unknown as { ImageCapture?: ImageCaptureConstructor }).ImageCapture
  if (track && ImageCapture) {
    try {
      return await imageBlobToImageData(await new ImageCapture(track).takePhoto())
    } catch {
      // Algunos móviles exponen ImageCapture pero rechazan takePhoto según el modo de cámara.
    }
  }
  return canvasVideoFrame(video)
}

// La unión mantiene la función fácil de sustituir en la orquestación síncrona de tests y permite que
// el navegador use la ruta asíncrona de ImageCapture sin cambiar el contrato observable del llamador.
export function grabVideoFrame(video: HTMLVideoElement): Promise<ImageData | null> | ImageData | null {
  return grabVideoFrameAsync(video)
}

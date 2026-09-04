// Normalización a JPEG (S2.2 decisión 8): tanto el frame capturado de la cámara en vivo como el
// fichero elegido por el selector nativo (fallback C3, que puede venir en HEIC/otro formato del
// móvil) se re-codifican aquí a `image/jpeg` antes de subir, cerrando el hueco que S2.1 dejó
// abierto explícitamente para formatos móviles.
const JPEG_QUALITY = 0.85

export function imageDataToJpegBlob(imageData: ImageData): Promise<Blob> {
  const canvas = document.createElement('canvas')
  canvas.width = imageData.width
  canvas.height = imageData.height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('No se pudo obtener el contexto 2D del canvas')
  ctx.putImageData(imageData, 0, 0)
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error('No se pudo generar el JPEG'))),
      'image/jpeg',
      JPEG_QUALITY,
    )
  })
}

/** Dibuja un `File`/`Blob` arbitrario (el selector de fichero nativo, C3) en un canvas y lo
 * re-codifica a JPEG — mismo destino final que `imageDataToJpegBlob`, entrada distinta. */
export async function fileToJpegBlob(file: Blob): Promise<Blob> {
  const bitmap = await createImageBitmap(file)
  try {
    const canvas = document.createElement('canvas')
    canvas.width = bitmap.width
    canvas.height = bitmap.height
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('No se pudo obtener el contexto 2D del canvas')
    ctx.drawImage(bitmap, 0, 0)
    return await new Promise((resolve, reject) => {
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error('No se pudo generar el JPEG'))),
        'image/jpeg',
        JPEG_QUALITY,
      )
    })
  } finally {
    bitmap.close()
  }
}

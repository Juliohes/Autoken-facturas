// Post-procesado de una captura ya hecha (S2.2 decisiones 6/8): si hay esquinas, recorta y endereza
// antes de normalizar a JPEG; si no, normaliza el frame completo tal cual (C8/C9, nunca bloquea por
// no encontrar bordes). Aparte de `CaptureScreen` para poder mockearlo entero en sus tests (jsdom no
// reproduce vídeo/canvas real).
import { warpToCorners } from './opencv/documentEdges'
import { loadOpenCv } from './opencv/loadOpenCv'
import { imageDataToJpegBlob } from './normalizeToJpeg'
import type { Corner } from './types'

export async function processCapturedFrame(frame: ImageData, corners: Corner[] | null): Promise<Blob> {
  if (!corners) return imageDataToJpegBlob(frame)
  const cv = await loadOpenCv()
  const warped = warpToCorners(cv, frame, corners)
  return imageDataToJpegBlob(warped)
}

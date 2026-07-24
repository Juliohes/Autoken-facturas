// Análisis de un frame ya capturado (S2.2): nitidez + esquinas de documento. Compartido entre el
// bucle en vivo (`useFrameAnalysisLoop`) y la captura manual (`CaptureScreen`), para no repetir la
// carga de OpenCV.js ni la orquestación blur+bordes en dos sitios.
import { computeBlurScore } from './opencv/blur'
import { detectDocumentCorners } from './opencv/documentEdges'
import { loadOpenCv } from './opencv/loadOpenCv'
import type { FrameAnalysis } from './types'

export async function analyzeFrame(frame: ImageData): Promise<FrameAnalysis> {
  const cv = await loadOpenCv()
  return { sharpness: computeBlurScore(cv, frame), corners: detectDocumentCorners(cv, frame) }
}

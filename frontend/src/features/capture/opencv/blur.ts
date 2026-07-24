// Puntuación de nitidez (S2.2 decisión 4): varianza del Laplaciano, técnica estándar de detección
// de blur — cuanto más alta, más nítida la imagen. Un valor bajo significa bordes poco marcados
// (típico de una foto desenfocada); un valor alto significa transiciones de contraste bruscas
// (típico de texto/bordes de documento en foco).
import type { CvModule } from './cvTypes'

export function computeBlurScore(cv: CvModule, imageData: ImageData): number {
  const src = cv.matFromImageData(imageData)
  const gray = new cv.Mat()
  const laplacian = new cv.Mat()
  const mean = new cv.Mat()
  const stddev = new cv.Mat()
  try {
    cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY)
    cv.Laplacian(gray, laplacian, cv.CV_64F)
    cv.meanStdDev(laplacian, mean, stddev)
    const stddevValue = stddev.data64F?.[0] ?? 0
    return stddevValue * stddevValue
  } finally {
    src.delete()
    gray.delete()
    laplacian.delete()
    mean.delete()
    stddev.delete()
  }
}

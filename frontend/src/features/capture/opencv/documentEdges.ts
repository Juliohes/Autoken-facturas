// Detección de bordes del documento + corrección de perspectiva (S2.2 decisiones 4 y 6): busca el
// contorno de 4 lados más grande del frame (el documento, asumiendo que ocupa la mayor parte de la
// imagen dentro del marco guía) y, si lo encuentra, endereza esa región a un rectángulo "de frente".
import type { Corner } from '../types'
import type { CvModule } from './cvTypes'
import { orderCorners } from './orderCorners'

// Un contorno de 4 lados que ocupe menos de esto del área total del frame se descarta: evita
// confundir un objeto pequeño y casual con el documento que se quiere capturar (spec §5, "detección
// de esquinas ambigua" se trata igual que "sin esquinas claras").
const MIN_DOCUMENT_AREA_RATIO = 0.15

export function detectDocumentCorners(cv: CvModule, imageData: ImageData): Corner[] | null {
  const src = cv.matFromImageData(imageData)
  const gray = new cv.Mat()
  const blurred = new cv.Mat()
  const edges = new cv.Mat()
  const hierarchy = new cv.Mat()
  const contours = new cv.MatVector()
  try {
    cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY)
    cv.GaussianBlur(gray, blurred, new cv.Size(5, 5), 0)
    cv.Canny(blurred, edges, 75, 200)
    cv.findContours(edges, contours, hierarchy, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE)

    const frameArea = imageData.width * imageData.height
    let best: Corner[] | null = null
    let bestArea = 0

    for (let i = 0; i < contours.size(); i++) {
      const contour = contours.get(i)
      const approx = new cv.Mat()
      try {
        const perimeter = cv.arcLength(contour, true)
        cv.approxPolyDP(contour, approx, 0.02 * perimeter, true)
        if (approx.rows !== 4) continue
        const area = cv.contourArea(approx)
        if (area <= bestArea || area / frameArea < MIN_DOCUMENT_AREA_RATIO) continue
        const points: Corner[] = []
        for (let p = 0; p < 4; p++) {
          points.push({ x: approx.data32S?.[p * 2] ?? 0, y: approx.data32S?.[p * 2 + 1] ?? 0 })
        }
        bestArea = area
        best = orderCorners(points as [Corner, Corner, Corner, Corner])
      } finally {
        approx.delete()
        contour.delete()
      }
    }
    return best
  } finally {
    src.delete()
    gray.delete()
    blurred.delete()
    edges.delete()
    hierarchy.delete()
    contours.delete()
  }
}

/** Distancia euclídea entre 2 esquinas, usada para calcular el tamaño del rectángulo de destino. */
function distance(a: Corner, b: Corner): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

/** Recorta y endereza `imageData` a un rectángulo "de frente" definido por las 4 esquinas (orden
 * canónico de `orderCorners`). El tamaño de destino se deriva de las propias esquinas (el lado más
 * largo de cada par, para no perder resolución al enderezar un documento fotografiado en ángulo). */
export function warpToCorners(cv: CvModule, imageData: ImageData, corners: Corner[]): ImageData {
  const [topLeft, topRight, bottomRight, bottomLeft] = corners
  const width = Math.round(Math.max(distance(topLeft, topRight), distance(bottomLeft, bottomRight)))
  const height = Math.round(Math.max(distance(topLeft, bottomLeft), distance(topRight, bottomRight)))

  const src = cv.matFromImageData(imageData)
  const dst = new cv.Mat()
  const srcPoints = cv.matFromArray(
    4,
    1,
    cv.CV_32FC2,
    [topLeft.x, topLeft.y, topRight.x, topRight.y, bottomRight.x, bottomRight.y, bottomLeft.x, bottomLeft.y],
  )
  const dstPoints = cv.matFromArray(4, 1, cv.CV_32FC2, [0, 0, width, 0, width, height, 0, height])
  const transform = cv.getPerspectiveTransform(srcPoints, dstPoints)
  try {
    cv.warpPerspective(src, dst, transform, new cv.Size(width, height))
    return new ImageData(new Uint8ClampedArray(dst.data), dst.cols, dst.rows)
  } finally {
    src.delete()
    dst.delete()
    srcPoints.delete()
    dstPoints.delete()
    transform.delete()
  }
}

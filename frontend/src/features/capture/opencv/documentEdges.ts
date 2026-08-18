// Detección de bordes del documento + corrección de perspectiva (S2.2 decisiones 4 y 6): busca el
// contorno candidato de mayor área del frame (el documento, asumiendo que ocupa la mayor parte de
// la imagen dentro del marco guía) y, si lo encuentra, endereza esa región a un rectángulo "de
// frente". Las 4 esquinas se recuperan con `approxPolyDP` y, si no da 4 vértices limpios, con
// `convexHull`/`minAreaRect` (S6.14 C3), nunca descartando un candidato válido solo por su forma.
import type { Corner } from '../types'
import type { CvMat, CvModule, CvRotatedRect } from './cvTypes'
import { orderCorners } from './orderCorners'

// Un contorno que ocupe menos de esto del área total del frame se descarta: evita confundir un
// objeto pequeño y casual con el documento que se quiere capturar (spec §5, "detección de esquinas
// ambigua" se trata igual que "sin esquinas claras": se sube el frame entero, sin recortar).
const MIN_DOCUMENT_AREA_RATIO = 0.15

// Kernel del cierre morfológico (S6.14 C3): pequeño a propósito, solo para unir bordes partidos por
// una sombra puntual, sin fusionar contornos que de verdad son distintos.
const MORPHOLOGICAL_CLOSE_KERNEL_SIZE = 3

/** Extrae un `Mat` de puntos `CV_32SC2` (como el que devuelve `approxPolyDP`) a `Corner[]`, o
 * `null` si no tiene exactamente 4 filas. */
function cornersFromPointMat(mat: CvMat): Corner[] | null {
  if (mat.rows !== 4) return null
  const points: Corner[] = []
  for (let p = 0; p < 4; p++) {
    points.push({ x: mat.data32S?.[p * 2] ?? 0, y: mat.data32S?.[p * 2 + 1] ?? 0 })
  }
  return orderCorners(points as [Corner, Corner, Corner, Corner])
}

/** Deriva las 4 esquinas de un `RotatedRect` (S6.14 C3, último recurso vía `minAreaRect`): fórmula
 * estándar de OpenCV (`RotatedRect::points()`), sin depender de `cv.boxPoints` (observado con
 * comportamiento inconsistente contra `@techstark/opencv-js`). */
function cornersFromRotatedRect(rect: CvRotatedRect): Corner[] {
  const angleRad = (rect.angle * Math.PI) / 180
  const b = Math.cos(angleRad) * 0.5
  const a = Math.sin(angleRad) * 0.5
  const { x: cx, y: cy } = rect.center
  const { width: w, height: h } = rect.size
  const p0: Corner = { x: cx - a * h - b * w, y: cy + b * h - a * w }
  const p1: Corner = { x: cx + a * h - b * w, y: cy - b * h - a * w }
  const p2: Corner = { x: 2 * cx - p0.x, y: 2 * cy - p0.y }
  const p3: Corner = { x: 2 * cx - p1.x, y: 2 * cy - p1.y }
  return orderCorners([p0, p1, p2, p3])
}

/** Recupera las 4 esquinas de un contorno candidato (S6.14 C3): si `approxPolyDP` no da
 * exactamente 4 vértices limpios, prueba la envolvente convexa (`convexHull`, corrige defectos
 * cóncavos de ruido) y, si tampoco da 4, usa el rectángulo envolvente rotado (`minAreaRect`) como
 * último recurso — nunca se descarta un candidato con área suficiente solo por su número de
 * vértices. */
function extractQuadrilateral(cv: CvModule, contour: CvMat): Corner[] | null {
  const approx = new cv.Mat()
  try {
    const perimeter = cv.arcLength(contour, true)
    cv.approxPolyDP(contour, approx, 0.02 * perimeter, true)
    const fromApprox = cornersFromPointMat(approx)
    if (fromApprox) return fromApprox

    const hull = new cv.Mat()
    const hullApprox = new cv.Mat()
    try {
      cv.convexHull(contour, hull, false, true)
      const hullPerimeter = cv.arcLength(hull, true)
      cv.approxPolyDP(hull, hullApprox, 0.02 * hullPerimeter, true)
      const fromHull = cornersFromPointMat(hullApprox)
      if (fromHull) return fromHull
    } finally {
      hull.delete()
      hullApprox.delete()
    }

    return cornersFromRotatedRect(cv.minAreaRect(contour))
  } finally {
    approx.delete()
  }
}

export function detectDocumentCorners(cv: CvModule, imageData: ImageData): Corner[] | null {
  const src = cv.matFromImageData(imageData)
  const gray = new cv.Mat()
  const blurred = new cv.Mat()
  const edges = new cv.Mat()
  const otsuMat = new cv.Mat()
  const morphKernel = cv.getStructuringElement(
    cv.MORPH_RECT,
    new cv.Size(MORPHOLOGICAL_CLOSE_KERNEL_SIZE, MORPHOLOGICAL_CLOSE_KERNEL_SIZE),
  )
  const hierarchy = new cv.Mat()
  const contours = new cv.MatVector()
  try {
    cv.cvtColor(src, gray, cv.COLOR_RGBA2GRAY)
    cv.GaussianBlur(gray, blurred, new cv.Size(5, 5), 0)
    // Umbral derivado de Otsu (S6.14 C3), no fijo: se adapta al contraste real de la propia
    // imagen (luz desigual, fotos oscuras) en vez de asumir un rango de contraste "típico".
    const otsuThreshold = cv.threshold(blurred, otsuMat, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
    cv.Canny(blurred, edges, otsuThreshold * 0.5, otsuThreshold)
    // Cierre morfológico (S6.14 C3): une bordes partidos por una sombra parcial antes de buscar
    // contornos, para no perder un lado del documento por un hueco pequeño.
    cv.morphologyEx(edges, edges, cv.MORPH_CLOSE, morphKernel)
    cv.findContours(edges, contours, hierarchy, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE)

    const frameArea = imageData.width * imageData.height
    let best: Corner[] | null = null
    let bestArea = 0

    for (let i = 0; i < contours.size(); i++) {
      const contour = contours.get(i)
      try {
        const area = cv.contourArea(contour)
        if (area <= bestArea || area / frameArea < MIN_DOCUMENT_AREA_RATIO) continue
        const points = extractQuadrilateral(cv, contour)
        if (!points) continue
        bestArea = area
        best = points
      } finally {
        contour.delete()
      }
    }
    return best
  } finally {
    src.delete()
    gray.delete()
    blurred.delete()
    edges.delete()
    otsuMat.delete()
    morphKernel.delete()
    hierarchy.delete()
    contours.delete()
  }
}

/** Distancia euclídea entre 2 esquinas, usada para calcular el tamaño del rectángulo de destino. */
function distance(a: Corner, b: Corner): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

// Suelo mínimo de resolución de salida (S6.14 C2): valor de diseño razonado, NO un DPI real
// derivado del tamaño físico del documento (no se conoce ese tamaño en la captura) — evita heredar
// un recorte pequeño de un encuadre lejano, sin pretender ser una medida de calidad de impresión.
export const MIN_LONG_EDGE_PX = 2200

/** Recorta y endereza `imageData` a un rectángulo "de frente" definido por las 4 esquinas (orden
 * canónico de `orderCorners`). El tamaño de destino se deriva de las propias esquinas (el lado más
 * largo de cada par, para no perder resolución al enderezar un documento fotografiado en ángulo);
 * si ese tamaño calculado queda por debajo del suelo mínimo (S6.14 C2), se escala hacia arriba
 * (interpolación cúbica) hasta alcanzarlo. Un rectángulo ya mayor que el suelo nunca se reduce. */
export function warpToCorners(cv: CvModule, imageData: ImageData, corners: Corner[]): ImageData {
  const [topLeft, topRight, bottomRight, bottomLeft] = corners
  let width = Math.round(Math.max(distance(topLeft, topRight), distance(bottomLeft, bottomRight)))
  let height = Math.round(Math.max(distance(topLeft, bottomLeft), distance(topRight, bottomRight)))
  const longEdge = Math.max(width, height)
  let interpolationFlags: number | undefined
  if (longEdge > 0 && longEdge < MIN_LONG_EDGE_PX) {
    const scale = MIN_LONG_EDGE_PX / longEdge
    width = Math.round(width * scale)
    height = Math.round(height * scale)
    interpolationFlags = cv.INTER_CUBIC
  }

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
    cv.warpPerspective(src, dst, transform, new cv.Size(width, height), interpolationFlags)
    return new ImageData(new Uint8ClampedArray(dst.data), dst.cols, dst.rows)
  } finally {
    src.delete()
    dst.delete()
    srcPoints.delete()
    dstPoints.delete()
    transform.delete()
  }
}

// Ordena 4 puntos cualesquiera al orden canónico (sup-izq, sup-der, inf-der, inf-izq) que usa el
// resto del módulo. Pura, sin OpenCV: `approxPolyDP` (documentEdges.ts) no garantiza ningún orden
// concreto de las 4 esquinas que encuentra, y `warpToCorners`/la revisión visual sí lo necesitan.
import type { Corner } from '../types'

export function orderCorners([a, b, c, d]: [Corner, Corner, Corner, Corner]): [
  Corner,
  Corner,
  Corner,
  Corner,
] {
  const points = [a, b, c, d]
  // sup-izq = suma x+y mínima; inf-der = suma x+y máxima.
  const bySum = [...points].sort((p, q) => p.x + p.y - (q.x + q.y))
  const topLeft = bySum[0]
  const bottomRight = bySum[3]
  // sup-der = diferencia x-y máxima; inf-izq = diferencia x-y mínima.
  const byDiff = [...points].sort((p, q) => p.x - p.y - (q.x - q.y))
  const bottomLeft = byDiff[0]
  const topRight = byDiff[3]
  return [topLeft, topRight, bottomRight, bottomLeft]
}

// Imágenes de muestra sintéticas para probar los algoritmos de OpenCV contra casos reales (S2.2
// decisión 10), generadas por código en vez de guardadas como binarios en el repo: deterministas,
// sin depender de una foto real, y fáciles de razonar (se sabe exactamente qué hay dibujado).
const WIDTH = 400
const HEIGHT = 300

/** Un rectángulo blanco nítido (el "documento") sobre fondo oscuro, con márgen — 4 esquinas claras
 * y bordes de alto contraste, ideal para blur alto y detección de contorno. */
export function makeDocumentImageData(): ImageData {
  const data = new Uint8ClampedArray(WIDTH * HEIGHT * 4)
  const margin = 40
  for (let y = 0; y < HEIGHT; y++) {
    for (let x = 0; x < WIDTH; x++) {
      const idx = (y * WIDTH + x) * 4
      const inDocument = x >= margin && x < WIDTH - margin && y >= margin && y < HEIGHT - margin
      const value = inDocument ? 250 : 20
      data[idx] = value
      data[idx + 1] = value
      data[idx + 2] = value
      data[idx + 3] = 255
    }
  }
  return new ImageData(data, WIDTH, HEIGHT)
}

/** Degradado suave sin ningún borde marcado: ni documento, ni un contorno de 4 lados grande, ni
 * transiciones de alto contraste (a diferencia de ruido de alta frecuencia, que SÍ puntuaría alto
 * en nitidez por varianza del Laplaciano — un degradado es el caso realista de "cámara apuntando a
 * una mesa/pared", sin nada que capturar). */
export function makeNoDocumentImageData(): ImageData {
  const data = new Uint8ClampedArray(WIDTH * HEIGHT * 4)
  for (let y = 0; y < HEIGHT; y++) {
    for (let x = 0; x < WIDTH; x++) {
      const idx = (y * WIDTH + x) * 4
      const value = Math.round((x / WIDTH) * 40) + 100
      data[idx] = value
      data[idx + 1] = value
      data[idx + 2] = value
      data[idx + 3] = 255
    }
  }
  return new ImageData(data, WIDTH, HEIGHT)
}

/** Documento con contraste desigual (S6.14 C3): dos zonas de brillo de fondo distintas (sombra
 * parcial) y un documento apenas 40 unidades más claro que el fondo local en cada zona — un umbral
 * de Canny fijo (75/200) no llega a detectar ese contorno de bajo contraste absoluto; uno derivado
 * de Otsu (relativo al histograma real de la imagen) sí. */
export function makeUnevenLightingDocumentImageData(): ImageData {
  const data = new Uint8ClampedArray(WIDTH * HEIGHT * 4)
  const margin = 40
  const contrast = 40
  for (let y = 0; y < HEIGHT; y++) {
    for (let x = 0; x < WIDTH; x++) {
      const idx = (y * WIDTH + x) * 4
      const inDocument = x >= margin && x < WIDTH - margin && y >= margin && y < HEIGHT - margin
      const localBackground = x < WIDTH / 2 ? 10 : 70
      const value = inDocument ? localBackground + contrast : localBackground
      data[idx] = value
      data[idx + 1] = value
      data[idx + 2] = value
      data[idx + 3] = 255
    }
  }
  return new ImageData(data, WIDTH, HEIGHT)
}

/** Documento con una esquina achaflanada (S6.14 C3): simula una esquina redondeada/imperfecta —
 * `approxPolyDP` da 5 vértices en vez de 4 (verificado empíricamente contra OpenCV.js real), así
 * que ejercita el fallback de `convexHull`/`minAreaRect` en vez del camino directo. */
export function makeRoundedCornerDocumentImageData(): ImageData {
  const data = new Uint8ClampedArray(WIDTH * HEIGHT * 4)
  const margin = 40
  const chamfer = 50
  const x0 = margin
  const x1 = WIDTH - margin
  const y0 = margin
  const y1 = HEIGHT - margin
  for (let y = 0; y < HEIGHT; y++) {
    for (let x = 0; x < WIDTH; x++) {
      const idx = (y * WIDTH + x) * 4
      const insideBaseRect = x >= x0 && x < x1 && y >= y0 && y < y1
      const inChamferedCorner = x > x1 - chamfer && y < y0 + chamfer && x1 - x + (y - y0) < chamfer
      const inDocument = insideBaseRect && !inChamferedCorner
      const value = inDocument ? 250 : 20
      data[idx] = value
      data[idx + 1] = value
      data[idx + 2] = value
      data[idx + 3] = 255
    }
  }
  return new ImageData(data, WIDTH, HEIGHT)
}

export const FIXTURE_WIDTH = WIDTH
export const FIXTURE_HEIGHT = HEIGHT

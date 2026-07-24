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

export const FIXTURE_WIDTH = WIDTH
export const FIXTURE_HEIGHT = HEIGHT

// Extiende `expect` de vitest con los matchers de jest-dom (toBeInTheDocument,
// toBeDisabled, toHaveTextContent...) y hace su augmentación de tipos visible al
// typecheck. Se carga en cada fichero de test vía `setupFiles`.
import '@testing-library/jest-dom/vitest'

// jsdom (el entorno de test) no implementa `ImageData` (S2.2: lo necesitan los algoritmos de
// OpenCV.js sobre imágenes de muestra). Un navegador real siempre la tiene; este polyfill mínimo
// solo cubre el constructor que usan los tests.
if (typeof globalThis.ImageData === 'undefined') {
  class ImageDataPolyfill {
    data: Uint8ClampedArray
    width: number
    height: number

    constructor(dataOrWidth: Uint8ClampedArray | number, widthOrHeight: number, height?: number) {
      if (dataOrWidth instanceof Uint8ClampedArray) {
        this.data = dataOrWidth
        this.width = widthOrHeight
        this.height = height ?? dataOrWidth.length / 4 / widthOrHeight
      } else {
        this.width = dataOrWidth
        this.height = widthOrHeight
        this.data = new Uint8ClampedArray(this.width * this.height * 4)
      }
    }
  }
  // @ts-expect-error polyfill mínimo, no implementa toda la interfaz de ImageData del DOM
  globalThis.ImageData = ImageDataPolyfill
}

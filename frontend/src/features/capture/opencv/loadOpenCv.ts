// Carga perezosa de OpenCV.js (S2.2 decisión 2): solo se importa al entrar en /capturar, nunca en
// el bundle principal — es un módulo WASM de varios MB, no debe penalizar el arranque del resto de
// la app. Patrón de arranque (thenable / onRuntimeInitialized) documentado por el propio paquete.
import type { CvModule } from './cvTypes'

interface EmscriptenModuleLike {
  then?: (cb: (v: unknown) => void) => void
  Mat?: unknown
  onRuntimeInitialized?: () => void
}

let cachedCv: Promise<CvModule> | null = null

export function loadOpenCv(): Promise<CvModule> {
  if (!cachedCv) {
    cachedCv = (async () => {
      const cvModule = ((await import('@techstark/opencv-js')) as { default: EmscriptenModuleLike })
        .default
      if (typeof cvModule.then === 'function') {
        return (await new Promise((resolve) => cvModule.then?.(resolve))) as unknown as CvModule
      }
      if (cvModule.Mat) {
        return cvModule as unknown as CvModule
      }
      await new Promise<void>((resolve) => {
        cvModule.onRuntimeInitialized = () => resolve()
      })
      return cvModule as unknown as CvModule
    })()
  }
  return cachedCv
}

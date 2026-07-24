// Cargador de OpenCV.js SOLO para tests (S2.2 decisión 10): carga el runtime WASM real (no un
// mock) para poder correr `computeBlurScore`/`detectDocumentCorners` contra imágenes de muestra de
// verdad. Usa `createRequire` en vez de `import()` a propósito: bajo Vitest, `import('@techstark/
// opencv-js')` lanza `TypeError: Method Promise.prototype.then called on incompatible receiver
// [object Module]` — el propio paquete expone un objeto "thenable" (patrón típico de fábricas
// Emscripten) que el interop ESM/CJS de Vite intenta auto-resolver como si fuera una Promise nativa
// y falla. `require()` (síncrono, CJS puro) evita esa capa de interop por completo; confirmado que
// funciona con un spike manual antes de escribir este módulo. El código de producción (bundle de
// navegador real) no sufre este problema y sigue usando `import()` normal — ver `loadOpenCv.ts`.
import { createRequire } from 'node:module'
import type { CvModule } from '../opencv/cvTypes'

let cachedCv: Promise<CvModule> | null = null

interface EmscriptenModuleLike {
  then?: (cb: (v: unknown) => void) => void
  Mat?: unknown
  onRuntimeInitialized?: () => void
}

export function loadOpenCvForTests(): Promise<CvModule> {
  if (!cachedCv) {
    cachedCv = (async () => {
      const require = createRequire(import.meta.url)
      const cvModule = require('@techstark/opencv-js') as EmscriptenModuleLike
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

// Tipos de dominio de la captura guiada (S2.2). Puros, sin dependencia de OpenCV ni del DOM, para
// que la orquestación (captureLoop.ts) se pueda testear sin cargar el runtime WASM.

/** Una esquina del documento detectada en el frame, en coordenadas de píxel de la imagen. */
export interface Corner {
  x: number
  y: number
}

/** Resultado de analizar un frame: nitidez + esquinas de documento, si se encontraron. */
export interface FrameAnalysis {
  /** Varianza del Laplaciano: a más alto, más nítido. */
  sharpness: number
  /** 4 esquinas del documento detectado, en orden (sup-izq, sup-der, inf-der, inf-izq), o `null`. */
  corners: Corner[] | null
}

export type Direction = 'recibida' | 'emitida'

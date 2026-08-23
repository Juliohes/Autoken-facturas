// Tipos de dominio de la captura guiada (S2.2). Puros, sin dependencia de OpenCV ni del DOM, para
// que la orquestación (captureLoop.ts) se pueda testear sin cargar el runtime WASM.

/** Una esquina del documento detectada en el frame, en coordenadas de píxel de la imagen. */
export interface Corner {
  x: number
  y: number
}

export type DetectionMethod = 'approx' | 'hull' | 'min_area_rect' | null

export interface NormalizedPoint {
  x: number
  y: number
}

export type NormalizedCorners = readonly [
  NormalizedPoint,
  NormalizedPoint,
  NormalizedPoint,
  NormalizedPoint,
]

export interface CaptureQuality {
  sharpness: number
  meanLuminance: number
  darkPixelRatio: number
  brightPixelRatio: number
  areaRatio: number
  detectionConfidence: number
  stabilityScore: number
  perspectiveScore: number
  clipped: boolean
}

/** Resultado de analizar un frame: nitidez + esquinas de documento, si se encontraron. */
export interface FrameAnalysis {
  /** Varianza del Laplaciano: a más alto, más nítido. */
  sharpness: number
  /** 4 esquinas del documento detectado, en orden (sup-izq, sup-der, inf-der, inf-izq), o `null`. */
  corners: Corner[] | null
  /** Metadatos del candidato seleccionado, disponibles cuando se usa el detector mejorado. */
  detectionConfidence?: number
  areaRatio?: number
  detectionMethod?: DetectionMethod
}

export type Direction = 'recibida' | 'emitida'

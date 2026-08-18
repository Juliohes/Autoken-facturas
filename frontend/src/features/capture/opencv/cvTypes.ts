// `@techstark/opencv-js` publica una referencia a `dist/src/types/opencv` que no existe en el
// paquete instalado (verificado: `find node_modules/@techstark/opencv-js/dist` no encuentra ese
// fichero) — los tipos oficiales están rotos en la versión publicada. En vez de pelear con eso o
// escribir cientos de líneas de declaraciones ambiente para toda la superficie de OpenCV, se tipa
// aquí SOLO lo que este módulo usa de verdad (ISP): un `Mat` opaco + las funciones concretas.
export interface CvMat {
  delete(): void
  rows: number
  cols: number
  /** Buffer de píxeles crudo (RGBA para un Mat de tipo CV_8UC4) — evita depender de un `<canvas>`
   * real para volver a sacar la imagen (jsdom no tiene renderizado de canvas de verdad). */
  data: Uint8Array
  data64F?: Float64Array
  data32S?: Int32Array
}

export interface CvSize {
  width: number
  height: number
}

/** Rectángulo rotado devuelto por `cv.minAreaRect` (S6.14 C3): objeto plano, no un `Mat`. */
export interface CvRotatedRect {
  center: { x: number; y: number }
  size: { width: number; height: number }
  angle: number
}

export interface CvModule {
  Mat: new (...args: unknown[]) => CvMat
  MatVector: new () => { size(): number; get(i: number): CvMat; delete(): void }
  matFromImageData(imageData: ImageData): CvMat
  cvtColor(src: CvMat, dst: CvMat, code: number): void
  GaussianBlur(src: CvMat, dst: CvMat, ksize: CvSize, sigmaX: number): void
  Laplacian(src: CvMat, dst: CvMat, ddepth: number): void
  meanStdDev(src: CvMat, mean: CvMat, stddev: CvMat): void
  /** Umbral de la imagen; devuelve el umbral calculado (relevante con `THRESH_OTSU`). */
  threshold(src: CvMat, dst: CvMat, thresh: number, maxval: number, type: number): number
  morphologyEx(src: CvMat, dst: CvMat, op: number, kernel: CvMat): void
  getStructuringElement(shape: number, ksize: CvSize): CvMat
  Canny(src: CvMat, dst: CvMat, threshold1: number, threshold2: number): void
  findContours(
    src: CvMat,
    contours: { size(): number; get(i: number): CvMat; delete(): void },
    hierarchy: CvMat,
    mode: number,
    method: number,
  ): void
  approxPolyDP(curve: CvMat, approxCurve: CvMat, epsilon: number, closed: boolean): void
  arcLength(curve: CvMat, closed: boolean): number
  contourArea(contour: CvMat): number
  /** `returnPoints=true` (S6.14 C3): la envolvente convexa como puntos, no como índices. */
  convexHull(points: CvMat, hull: CvMat, clockwise?: boolean, returnPoints?: boolean): void
  minAreaRect(points: CvMat): CvRotatedRect
  matFromArray(rows: number, cols: number, type: number, data: number[]): CvMat
  getPerspectiveTransform(src: CvMat, dst: CvMat): CvMat
  warpPerspective(src: CvMat, dst: CvMat, M: CvMat, dsize: CvSize, flags?: number): void
  Size: new (width: number, height: number) => CvSize
  CV_64F: number
  CV_32FC2: number
  COLOR_RGBA2GRAY: number
  RETR_LIST: number
  CHAIN_APPROX_SIMPLE: number
  THRESH_BINARY: number
  THRESH_OTSU: number
  MORPH_CLOSE: number
  MORPH_RECT: number
  INTER_CUBIC: number
}

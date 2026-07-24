// Bucle de análisis de frames en vivo (S2.2, C4-C6): mientras la cámara está activa, analiza un
// frame del vídeo a intervalos regulares (nitidez + esquinas de documento) y entrega el resultado
// vía `onAnalysis`. No se prueba en detalle aquí (jsdom no reproduce vídeo real ni renderiza
// `<canvas>`, S2.2 §6): la orquestación que consume sus resultados (`captureLoop.ts`) sí está
// probada, inyectando `FrameAnalysis` de mentira — este hook se mockea entero en `CaptureScreen`.
import { useEffect, useRef } from 'react'

import { analyzeFrame } from './analyzeFrame'
import { grabVideoFrame } from './grabVideoFrame'
import type { FrameAnalysis } from './types'

const ANALYSIS_INTERVAL_MS = 400

export function useFrameAnalysisLoop(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  active: boolean,
  // Entrega también el `frame` que se acaba de analizar (no solo el resultado): quien reciba la
  // auto-captura necesita esos mismos píxeles para el recorte/perspectiva (hallazgo de auditoría —
  // antes se perdían en la costura entre este hook y `CaptureScreen`, dejando la auto-captura sin
  // foto que mostrar).
  onAnalysis: (analysis: FrameAnalysis, frame: ImageData) => void,
): void {
  const onAnalysisRef = useRef(onAnalysis)
  onAnalysisRef.current = onAnalysis

  useEffect(() => {
    if (!active) return undefined
    let cancelled = false

    const timer = setInterval(() => {
      void (async () => {
        const video = videoRef.current
        if (!video) return
        const frame = grabVideoFrame(video)
        if (!frame) return
        const analysis = await analyzeFrame(frame)
        if (!cancelled) onAnalysisRef.current(analysis, frame)
      })()
    }, ANALYSIS_INTERVAL_MS)

    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [active, videoRef])
}

const CAPTURE_MARK_PREFIX = 'autoken.capture'

export type CaptureTimingPhase = 'frame' | 'analysis' | 'processing' | 'preview'

/** Marcas locales de rendimiento, sin enviar imágenes ni datos fiscales. */
export function startCaptureTiming() {
  const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
  const start = `${CAPTURE_MARK_PREFIX}.${id}.start`
  mark(start)

  return {
    mark(phase: CaptureTimingPhase) {
      const end = `${CAPTURE_MARK_PREFIX}.${id}.${phase}`
      mark(end)
      measure(`${CAPTURE_MARK_PREFIX}.${phase}`, start, end)
    },
  }
}

function mark(name: string) {
  if (typeof performance !== 'undefined' && typeof performance.mark === 'function') performance.mark(name)
}

function measure(name: string, start: string, end: string) {
  if (typeof performance !== 'undefined' && typeof performance.measure === 'function') {
    try {
      performance.measure(name, start, end)
    } catch {
      // Algunos navegadores eliminan marcas automáticamente; la captura no depende de la telemetría.
    }
  }
}

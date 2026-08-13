// Ciclo de vida de la cámara (S2.2, C2/C3): pide la cámara trasera al montar; si no hay soporte,
// se deniega el permiso, o falla por cualquier motivo, cae a "unavailable" (la pantalla de captura
// usa entonces el selector de fichero nativo). Libera siempre el stream al desmontar.
import { useEffect, useRef, useState } from 'react'

const CAMERA_REQUEST_TIMEOUT_MS = 10_000

export type CameraStatus = 'requesting' | 'active' | 'unavailable'

export interface CameraStreamState {
  status: CameraStatus
  stream: MediaStream | null
  canRetry: boolean
  unavailableReason: 'insecure' | 'unavailable' | null
  retry: () => void
}

export function useCameraStream(): CameraStreamState {
  const [status, setStatus] = useState<CameraStatus>('requesting')
  const [stream, setStream] = useState<MediaStream | null>(null)
  const [attempt, setAttempt] = useState(0)
  const [unavailableReason, setUnavailableReason] = useState<'insecure' | 'unavailable' | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const requestingRef = useRef(true)
  const isSecure = window.isSecureContext !== false
  const canRetry = isSecure && Boolean(navigator.mediaDevices?.getUserMedia)

  useEffect(() => {
    let cancelled = false
    let timedOut = false

    const stop = (media: MediaStream | null) => media?.getTracks().forEach((track) => track.stop())
    const timeout = window.setTimeout(() => {
      timedOut = true
      requestingRef.current = false
      setUnavailableReason('unavailable')
      setStatus('unavailable')
    }, CAMERA_REQUEST_TIMEOUT_MS)

    void (async () => {
      if (!canRetry) {
        window.clearTimeout(timeout)
        if (!cancelled) {
          setUnavailableReason(isSecure ? 'unavailable' : 'insecure')
          setStatus('unavailable')
        }
        return
      }
      try {
        // La trasera mejora la experiencia móvil, pero no es una condición para poder capturar: una
        // webcam o la única cámara disponible sigue siendo una cámara válida (S6.9 C1).
        let media: MediaStream
        try {
          media = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: { exact: 'environment' } },
            audio: false,
          })
        } catch (error) {
          // Solo la ausencia de lente trasera permite probar otra cámara. Repetir una petición tras
          // un permiso denegado no ayuda al usuario y puede provocar dos avisos del navegador.
          if (!(error instanceof DOMException) || !['OverconstrainedError', 'NotFoundError'].includes(error.name)) throw error
          media = await navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        }
        if (cancelled || timedOut) {
          stop(media)
          return
        }
        streamRef.current = media
        setUnavailableReason(null)
        setStream(media)
        setStatus('active')
      } catch {
        if (!cancelled && !timedOut) {
          setUnavailableReason('unavailable')
          setStatus('unavailable')
        }
      } finally {
        window.clearTimeout(timeout)
        requestingRef.current = false
      }
    })()

    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [attempt, canRetry, isSecure])

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  // Si el hardware falla o el SO revoca el permiso en caliente (spec §5), el track termina solo:
  // sin esto la vista previa se quedaría congelada sin que la app lo note. Cae al mismo camino que
  // "sin cámara" (C3, selector de fichero) en vez de fingir que sigue en vivo.
  useEffect(() => {
    if (!stream) return undefined
    const tracks = stream.getTracks()
    const handleEnded = () => {
      // Un evento tardío de un stream ya sustituido no puede invalidar ni perder la referencia al
      // stream nuevo. El antiguo se detiene completo antes de pasar al fallback.
      if (streamRef.current !== stream) return
      streamRef.current = null
      stream.getTracks().forEach((track) => track.stop())
      setStream(null)
      setUnavailableReason('unavailable')
      setStatus('unavailable')
    }
    tracks.forEach((track) => track.addEventListener('ended', handleEnded))
    return () => {
      tracks.forEach((track) => track.removeEventListener('ended', handleEnded))
    }
  }, [stream])

  const retry = () => {
    if (!canRetry || requestingRef.current) return
    requestingRef.current = true
    const previousStream = streamRef.current
    streamRef.current = null
    previousStream?.getTracks().forEach((track) => track.stop())
    setStream(null)
    setUnavailableReason(null)
    setStatus('requesting')
    setAttempt((current) => current + 1)
  }

  return { status, stream, canRetry, unavailableReason, retry }
}

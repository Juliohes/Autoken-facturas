// Ciclo de vida de la cámara (S2.2, C2/C3): pide la cámara trasera al montar; si no hay soporte,
// se deniega el permiso, o falla por cualquier motivo, cae a "unavailable" (la pantalla de captura
// usa entonces el selector de fichero nativo). Libera siempre el stream al desmontar.
import { useEffect, useState } from 'react'

export type CameraStatus = 'requesting' | 'active' | 'unavailable'

export interface CameraStreamState {
  status: CameraStatus
  stream: MediaStream | null
}

export function useCameraStream(): CameraStreamState {
  const [status, setStatus] = useState<CameraStatus>('requesting')
  const [stream, setStream] = useState<MediaStream | null>(null)

  useEffect(() => {
    let cancelled = false

    void (async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        if (!cancelled) setStatus('unavailable')
        return
      }
      try {
        const media = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: 'environment' },
          audio: false,
        })
        if (cancelled) {
          media.getTracks().forEach((track) => track.stop())
          return
        }
        setStream(media)
        setStatus('active')
      } catch {
        if (!cancelled) setStatus('unavailable')
      }
    })()

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    return () => {
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [stream])

  // Si el hardware falla o el SO revoca el permiso en caliente (spec §5), el track termina solo:
  // sin esto la vista previa se quedaría congelada sin que la app lo note. Cae al mismo camino que
  // "sin cámara" (C3, selector de fichero) en vez de fingir que sigue en vivo.
  useEffect(() => {
    if (!stream) return undefined
    const tracks = stream.getTracks()
    const handleEnded = () => setStatus('unavailable')
    tracks.forEach((track) => track.addEventListener('ended', handleEnded))
    return () => {
      tracks.forEach((track) => track.removeEventListener('ended', handleEnded))
    }
  }, [stream])

  return { status, stream }
}

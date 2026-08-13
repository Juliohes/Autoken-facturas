// Pantalla de captura guiada (S2.2). Orquesta cámara/fallback de fichero, auto-captura, revisión y
// subida; la lógica de decisión vive en módulos puros aparte (`captureLoop.ts`, `uploadErrors.ts`,
// `captureSelectors.ts`, `processCapture.ts`), sin monolito. Comportamientos C1-C14 de la spec.
import { useEffect, useReducer, useRef, useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'

import { ROUTES } from '../../app/routes'
import { useCompanyOptions } from '../companies/useCompanyOptions'
import { useSession } from '../session/SessionProvider'
import { analyzeFrame } from './analyzeFrame'
import { captureReducer, INITIAL_CAPTURE_STATE } from './captureLoop'
import { describeUploadState, resolveEffectiveCompanyId } from './captureSelectors'
import { grabVideoFrame } from './grabVideoFrame'
import { fileToJpegBlob } from './normalizeToJpeg'
import { processCapturedFrame } from './processCapture'
import type { Direction } from './types'
import { useCameraStream } from './useCameraStream'
import { useUploadCapture } from './useUploadCapture'

interface Props {
  onUploaded: (fileId: string, direction: Direction) => void
}

export function CaptureScreen({ onUploaded }: Props) {
  const { user } = useSession()
  const role = user?.role
  const camera = useCameraStream()
  const videoRef = useRef<HTMLVideoElement>(null)
  // Los píxeles de la captura en curso viven fuera del reducer: son pesados y no forman parte de su
  // decisión pura. El contador descarta resultados asíncronos de una captura anterior.
  const capturedFrameRef = useRef<ImageData | null>(null)
  const captureOperationRef = useRef(0)

  const [captureState, dispatch] = useReducer(captureReducer, INITIAL_CAPTURE_STATE)
  const [direction, setDirection] = useState<Direction>('recibida')
  const [companyId, setCompanyId] = useState('')
  const [reviewBlob, setReviewBlob] = useState<Blob | null>(null)
  const [reviewUrl, setReviewUrl] = useState<string | null>(null)
  const [processing, setProcessing] = useState(false)
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [videoReady, setVideoReady] = useState(false)

  const companies = useCompanyOptions({ enabled: role === 'tenant_admin' })
  const upload = useUploadCapture()

  useEffect(() => {
    setVideoReady(false)
    if (videoRef.current) videoRef.current.srcObject = camera.stream
  }, [camera.stream])

  const markVideoReady = () => {
    const video = videoRef.current
    setVideoReady(Boolean(video && video.videoWidth > 0 && video.videoHeight > 0))
  }

  // Recorta/normaliza la captura de CÁMARA (auto o manual) a JPEG. El fallback de fichero (C3) no
  // pasa por aquí: ya deja `reviewBlob` listo él mismo en `handleFileSelected`, sin frame que
  // procesar (`capturedFrameRef.current` queda `null` a propósito en ese camino).
  useEffect(() => {
    if (captureState.phase !== 'captured' || !capturedFrameRef.current) return
    const frame = capturedFrameRef.current
    const operation = captureOperationRef.current
    setProcessing(true)
    setReviewBlob(null)
    void processCapturedFrame(frame, captureState.corners)
      .then((blob) => {
        if (captureOperationRef.current === operation) setReviewBlob(blob)
      })
      .finally(() => {
        if (captureOperationRef.current === operation) setProcessing(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [captureState])

  // La vista previa de la foto capturada usa una URL de objeto propia, revocada al cambiar de blob
  // o desmontar (hallazgo de auditoría: antes se creaba una URL nueva en cada render sin liberar
  // nunca la anterior).
  useEffect(() => {
    if (!reviewBlob) {
      setReviewUrl(null)
      return undefined
    }
    const url = URL.createObjectURL(reviewBlob)
    setReviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [reviewBlob])

  const handleManualCapture = async () => {
    const frame = grabVideoFrame(videoRef.current as HTMLVideoElement)
    if (!frame) {
      // Defensa adicional ante una revocación entre habilitar el botón y el clic: nunca se procesa
      // un frame vacío, aunque el navegador deje de entregar píxeles justo en ese instante.
      setVideoReady(false)
      return
    }
    const operation = captureOperationRef.current + 1
    captureOperationRef.current = operation
    setCaptureError(null)
    setProcessing(true)
    capturedFrameRef.current = frame
    camera.close()
    const analysis = await analyzeFrame(frame)
    if (captureOperationRef.current !== operation) return
    dispatch({ type: 'manual_capture', analysis })
  }

  const handleFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    // Elegir un archivo sustituye la cámara igual que tomar una foto: nunca se mantiene un stream
    // encendido detrás de la revisión, aunque el selector se haya abierto desde el overlay.
    camera.close()
    const operation = captureOperationRef.current + 1
    captureOperationRef.current = operation
    setCaptureError(null)
    setProcessing(true)
    try {
      const blob = await fileToJpegBlob(file)
      if (captureOperationRef.current !== operation) return
      capturedFrameRef.current = null
      setReviewBlob(blob)
      dispatch({ type: 'manual_capture', analysis: null })
    } catch {
      // `createImageBitmap` rechaza si el fichero elegido no es una imagen decodificable
      // (`accept="image/*"` es solo una pista de UI, saltable) — nunca se avanza a la revisión sin
      // una foto real que mostrar (hallazgo de auditoría de seguridad).
      setCaptureError('Ese fichero no es una imagen válida. Elige otra foto.')
    } finally {
      setProcessing(false)
    }
  }

  const handleRetake = () => {
    camera.close()
    captureOperationRef.current += 1
    capturedFrameRef.current = null
    setReviewBlob(null)
    setCaptureError(null)
    dispatch({ type: 'retake' })
  }

  const effectiveCompanyId = resolveEffectiveCompanyId(role, user?.company?.id, companyId)
  const canUpload = reviewBlob !== null && effectiveCompanyId !== '' && !upload.isPending

  const handleUseThisPhoto = () => {
    if (!reviewBlob || !effectiveCompanyId) return
    upload.mutate(
      { blob: reviewBlob, companyId: effectiveCompanyId },
      { onSuccess: (data) => onUploaded(data.id, direction) },
    )
  }

  const uploadState = describeUploadState(upload.error, upload.isError)

  // Spec §5 "sesión user sin empresa asignada": se trata igual que un fallo de identidad, sin
  // llegar a mostrar cámara ni selector de fichero (hallazgo de auditoría, coincidente en dos
  // lentes). Tras todos los hooks (regla de hooks de React: nunca antes de llamarlos todos).
  if (role === 'user' && !user?.company) {
    return (
      <div className="p-6">
        <p className="text-red-400" role="alert">
          No se pudo cargar tu empresa. Inténtalo de nuevo más tarde.
        </p>
      </div>
    )
  }

  // Antes: círculo de radio nativo (diminuto, mal objetivo táctil en móvil) + texto plano.
  // Ahora: el radio sigue existiendo (accesibilidad + `getByRole('radio', ...)` de los tests),
  // pero oculto (`sr-only`); la propia etiqueta se estiliza como un botón-píldora completo, con
  // `has-[:checked]` marcando cuál de los dos está activo. Más grande (2026-08-02, a petición de
  // Julio): mejor objetivo táctil en móvil, donde vive este flujo.
  const directionButtonClass =
    'cursor-pointer rounded-full border border-slate-600 px-6 py-3 text-base font-medium ' +
    'text-slate-200 has-[:checked]:border-emerald-500 has-[:checked]:bg-emerald-600 ' +
    'has-[:checked]:text-white'

  // Selector de fichero del dispositivo (2026-08-02, a petición de Julio): antes solo existía como
  // alternativa cuando la cámara fallaba (C3); ahora es un botón propio, siempre disponible junto a
  // "Tomar foto" — subir una foto ya existente del carrete es un camino legítimo, no solo un
  // fallback. Sin `capture="environment"` a propósito: ese atributo empuja a algunos navegadores
  // móviles a abrir la cámara directamente, justo lo que este botón NO debe hacer (para eso está
  // "Tomar foto") — este abre el selector de ficheros del dispositivo (galería/archivos).
  const FilePickerButton = (
    <label className="flex cursor-pointer items-center justify-center rounded-md border border-slate-600 px-4 py-3 text-base font-medium text-slate-100 hover:bg-slate-800">
      Subir archivo
      <input
        type="file"
        aria-label="Elige o toma una foto"
        accept="image/*"
        onChange={(e) => void handleFileSelected(e)}
        className="sr-only"
      />
    </label>
  )

  const CameraProblem = (
    <p className="text-slate-400">
      {camera.unavailableReason === 'insecure'
        ? 'La cámara requiere una conexión segura. Puedes subir una foto desde tu dispositivo.'
        : 'No se pudo acceder a la cámara. Elige o toma una foto con tu dispositivo.'}
    </p>
  )

  const DirectionSelector = (
    <fieldset className="flex gap-3 text-sm text-slate-200">
      <legend className="sr-only">Dirección</legend>
      <label className={directionButtonClass}>
        <input
          type="radio"
          name="direction"
          className="sr-only"
          checked={direction === 'recibida'}
          onChange={() => setDirection('recibida')}
        />
        Recibida
      </label>
      <label className={directionButtonClass}>
        <input
          type="radio"
          name="direction"
          className="sr-only"
          checked={direction === 'emitida'}
          onChange={() => setDirection('emitida')}
        />
        Emitida
      </label>
    </fieldset>
  )

  if (captureState.phase === 'captured') {
    return (
      <section className="mx-auto max-w-xl space-y-4 p-6 text-slate-100">
        <h1 className="text-xl font-semibold">Revisar foto</h1>
        {DirectionSelector}

        {processing && <p className="text-slate-400">Procesando…</p>}

        {!processing && reviewUrl && (
          <img src={reviewUrl} alt="Foto capturada" className="w-full rounded border border-slate-700" />
        )}

        {captureState.wasBlurry && (
          <p role="alert" className="text-sm text-amber-400">
            La foto puede salir borrosa. Puedes usarla igual o repetirla.
          </p>
        )}

        {role === 'tenant_admin' && (
          <label className="flex flex-col text-sm text-slate-300">
            Empresa
            <select
              value={companyId}
              onChange={(e) => setCompanyId(e.target.value)}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
            >
              <option value="">Elige una empresa</option>
              {(companies.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}

        {uploadState.message && (
          <p role="alert" className="text-sm text-red-400">
            {uploadState.message}
          </p>
        )}

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={handleRetake}
            className="rounded-md border border-slate-600 px-4 py-2 text-slate-100"
          >
            Repetir
          </button>
          <button
            type="button"
            onClick={handleUseThisPhoto}
            disabled={!canUpload || processing}
            className="rounded-md bg-emerald-600 px-4 py-2 font-medium text-white disabled:opacity-40"
          >
            {upload.isPending ? 'Subiendo…' : 'Usar esta foto'}
          </button>
          {uploadState.retryable && uploadState.message && (
            <button
              type="button"
              onClick={handleUseThisPhoto}
              className="rounded-md border border-slate-600 px-4 py-2 text-slate-100"
            >
              Reintentar
            </button>
          )}
        </div>
      </section>
    )
  }

  return (
    <section className="mx-auto max-w-xl space-y-4 p-6 text-slate-100">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Capturar factura</h1>
        {/* "Historial" deja de ser una entrada propia del menú (2026-08-01, a petición de Julio):
            vive aquí dentro, junto a la tarea principal del día a día de este rol (S2.2). Estilo de
            botón (2026-08-02, a petición de Julio, "vivo y a mano"): más visible que un enlace
            subrayado suelto, sin dejar de ser el mismo `<Link>` (mismo `role="link"`, mismos tests). */}
        <Link
          to={ROUTES.history}
          className="rounded-md border border-emerald-600 px-3 py-1.5 text-sm font-medium text-emerald-400 hover:bg-emerald-600/10"
        >
          Ver historial
        </Link>
      </div>
      {DirectionSelector}

      {captureError && (
        <p role="alert" className="text-sm text-red-400">
          {captureError}
        </p>
      )}

      {processing && camera.status === 'idle' && <p className="text-slate-400">Preparando foto...</p>}

      {!processing && camera.status === 'idle' && (
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={camera.open}
            className="rounded-md bg-emerald-600 px-4 py-3 text-base font-semibold text-white"
          >
            Abrir cámara
          </button>
          {FilePickerButton}
        </div>
      )}

      {camera.status !== 'idle' && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Cámara para capturar factura"
          className="fixed inset-0 z-50 flex min-h-screen flex-col bg-slate-950 p-4 text-slate-100"
        >
          <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-4">
            {camera.status === 'requesting' && <p className="text-center text-slate-300">Pidiendo acceso a la cámara…</p>}
            {camera.status === 'active' && (
              <div className="relative mx-auto w-full max-w-xl overflow-hidden rounded-lg bg-black">
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  onLoadedData={markVideoReady}
                  onLoadedMetadata={markVideoReady}
                  className="max-h-[70vh] w-full object-contain"
                />
                <div
                  data-testid="camera-guide-frame"
                  aria-hidden="true"
                  className="pointer-events-none absolute left-1/2 top-1/2 h-[72vh] max-w-[78vw] -translate-x-1/2 -translate-y-1/2 aspect-[1/1.414] rounded border-4 border-emerald-400 shadow-[0_0_0_9999px_rgb(0_0_0_/_0.35)]"
                />
              </div>
            )}
            {camera.status === 'unavailable' && CameraProblem}
            <div className="mx-auto flex w-full max-w-xl flex-wrap gap-3">
              {camera.status === 'active' && (
                <button
                  type="button"
                  onClick={() => void handleManualCapture()}
                  disabled={!videoReady}
                  className="flex-1 rounded-md bg-emerald-600 px-4 py-4 text-lg font-semibold text-white disabled:opacity-40"
                >
                  {videoReady ? 'Tomar foto' : 'Preparando cámara…'}
                </button>
              )}
              {camera.status === 'active' && !videoReady && camera.canRetry && (
                <button type="button" onClick={camera.retry} className="rounded-md border border-slate-600 px-4 py-3 font-medium">
                  Reintentar cámara
                </button>
              )}
              {camera.status !== 'active' && camera.canRetry && (
                <button type="button" onClick={camera.retry} className="rounded-md border border-slate-600 px-4 py-3 font-medium">
                  Reintentar cámara
                </button>
              )}
              {FilePickerButton}
              <button type="button" onClick={camera.close} className="rounded-md border border-slate-600 px-4 py-3 font-medium">
                Cerrar cámara
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

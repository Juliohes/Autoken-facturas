// Pantalla de captura guiada (S2.2). Orquesta cámara/fallback de fichero, auto-captura, revisión y
// subida; la lógica de decisión vive en módulos puros aparte (`captureLoop.ts`, `uploadErrors.ts`,
// `captureSelectors.ts`, `processCapture.ts`), sin monolito. Comportamientos C1-C14 de la spec.
//
// Experimento 2026-08-01 (rama experiment/setex-user-ui-v1): anatomía y estilo visual de
// HIPERDOC-FRONTEND-USUARIO-v1-setex1.md §03/§06 — tarjeta clara, cabecera con el logotipo SETEX,
// chip de empresa con color determinista, selector Recibida/Emitida con los colores exactos del
// documento. La LÓGICA (cámara, OpenCV, subida) no cambia ni una línea, solo el JSX/estilos.
import { useEffect, useReducer, useRef, useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'

import { ROUTES } from '../../app/routes'
import { SetexBadge } from '../../shared/SetexBadge'
import { setexCompanyColor } from '../../shared/setexCompanyColor'
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
import { useFrameAnalysisLoop } from './useFrameAnalysisLoop'
import { useUploadCapture } from './useUploadCapture'

interface Props {
  onUploaded: (fileId: string, direction: Direction) => void
}

export function CaptureScreen({ onUploaded }: Props) {
  const { user, logout } = useSession()
  const role = user?.role
  const camera = useCameraStream()
  const videoRef = useRef<HTMLVideoElement>(null)
  // Los píxeles de la captura en curso (origen cámara) viven en un ref, no en el estado del
  // reducer: son datos pesados que no aportan nada a la decisión pura de `captureLoop.ts` y
  // romperían sus comparaciones `toEqual` en los tests. Se rellena en el MISMO callback que
  // despacha la acción correspondiente (auto-captura y captura manual), nunca después — así nunca
  // queda desincronizado con la fase del reducer (hallazgo de auditoría: antes solo se rellenaba en
  // la captura manual, dejando la auto-captura sin foto que procesar).
  const capturedFrameRef = useRef<ImageData | null>(null)

  const [captureState, dispatch] = useReducer(captureReducer, INITIAL_CAPTURE_STATE)
  const [direction, setDirection] = useState<Direction>('recibida')
  const [companyId, setCompanyId] = useState('')
  const [reviewBlob, setReviewBlob] = useState<Blob | null>(null)
  const [reviewUrl, setReviewUrl] = useState<string | null>(null)
  const [processing, setProcessing] = useState(false)
  const [captureError, setCaptureError] = useState<string | null>(null)

  const companies = useCompanyOptions({ enabled: role === 'tenant_admin' })
  const upload = useUploadCapture()

  const liveAnalysisActive = camera.status === 'active' && captureState.phase === 'live'
  useFrameAnalysisLoop(videoRef, liveAnalysisActive, (analysis, frame) => {
    capturedFrameRef.current = frame
    dispatch({ type: 'frame_analyzed', analysis })
  })

  useEffect(() => {
    if (videoRef.current) videoRef.current.srcObject = camera.stream
  }, [camera.stream])

  // Recorta/normaliza la captura de CÁMARA (auto o manual) a JPEG. El fallback de fichero (C3) no
  // pasa por aquí: ya deja `reviewBlob` listo él mismo en `handleFileSelected`, sin frame que
  // procesar (`capturedFrameRef.current` queda `null` a propósito en ese camino).
  useEffect(() => {
    if (captureState.phase !== 'captured' || !capturedFrameRef.current) return
    const frame = capturedFrameRef.current
    setProcessing(true)
    setReviewBlob(null)
    void processCapturedFrame(frame, captureState.corners)
      .then(setReviewBlob)
      .finally(() => setProcessing(false))
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
      // La cámara todavía no ha entregado ningún frame real (vídeo aún cargando metadatos) —
      // nunca se despacha una captura sin datos que procesar (hallazgo de auditoría de seguridad).
      setCaptureError('La cámara todavía se está preparando. Espera un momento e inténtalo de nuevo.')
      return
    }
    setCaptureError(null)
    capturedFrameRef.current = frame
    const analysis = await analyzeFrame(frame)
    dispatch({ type: 'manual_capture', analysis })
  }

  const handleFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    setCaptureError(null)
    setProcessing(true)
    try {
      const blob = await fileToJpegBlob(file)
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

  const companyColor = user?.company ? setexCompanyColor(user.company.name) : null
  const cardBorderColor = companyColor?.dark ?? '#667eea'

  // Cabecera: logotipo + «Facturas» + botón rojo Salir (§06 punto 1, presente en toda pantalla).
  const Header = (
    <header className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <SetexBadge />
        <h1 className="text-[1.6em] font-bold text-sx-ink1">Facturas</h1>
      </div>
      <button
        type="button"
        onClick={() => void logout()}
        className="rounded-md bg-sx-bad px-3 py-1.5 text-sm font-semibold text-white"
      >
        Salir
      </button>
    </header>
  )

  // Chip de empresa (§06 punto 2): oculto para administradores, color determinista.
  const CompanyChip = user?.company && companyColor && (
    <div
      className="mt-3 inline-block max-w-full truncate rounded-full px-4 py-1 text-sm font-medium text-white shadow-sm"
      style={{ background: `linear-gradient(135deg, ${companyColor.light}, ${companyColor.dark})` }}
    >
      {user.company.name}
    </div>
  )

  // Antes: círculo de radio nativo (diminuto, mal objetivo táctil en móvil) + texto plano.
  // Ahora: el radio sigue existiendo (accesibilidad + `getByRole('radio', ...)` de los tests),
  // pero oculto (`sr-only`); la propia etiqueta es un botón-píldora completo con los colores
  // exactos de §06 (Recibida azul, Emitida verde, inactivo gris).
  const DirectionSelector = (
    <fieldset className="mt-4 grid grid-cols-2 gap-3 text-sm">
      <legend className="sr-only">Dirección</legend>
      <label
        className="cursor-pointer rounded-lg border-2 px-3 py-2 text-center font-medium transition"
        style={
          direction === 'recibida'
            ? { background: '#ebf8ff', borderColor: '#4299e1', color: '#2b6cb0', boxShadow: '0 0 0 2px #4299e1' }
            : { background: '#f7fafc', borderColor: '#e2e8f0', color: '#a0aec0' }
        }
      >
        <input
          type="radio"
          name="direction"
          className="sr-only"
          checked={direction === 'recibida'}
          onChange={() => setDirection('recibida')}
        />
        📥 Factura Recibida
      </label>
      <label
        className="cursor-pointer rounded-lg border-2 px-3 py-2 text-center font-medium transition"
        style={
          direction === 'emitida'
            ? { background: '#f0fff4', borderColor: '#48bb78', color: '#276749', boxShadow: '0 0 0 2px #48bb78' }
            : { background: '#f7fafc', borderColor: '#e2e8f0', color: '#a0aec0' }
        }
      >
        <input
          type="radio"
          name="direction"
          className="sr-only"
          checked={direction === 'emitida'}
          onChange={() => setDirection('emitida')}
        />
        📤 Factura Emitida
      </label>
    </fieldset>
  )

  if (captureState.phase === 'captured') {
    return (
      <div className="mx-auto w-[90%] max-w-[600px] py-6">
        <div
          className="space-y-4 rounded-xl border-t-4 bg-gradient-to-b from-[#fafafa] via-[#f5f5f5] to-[#f0f0f0] p-5 text-sx-ink1 shadow-[0_8px_30px_rgba(0,0,0,.15)]"
          style={{ borderTopColor: cardBorderColor }}
        >
          {Header}
          {CompanyChip}
          <h2 className="text-[1.2em] font-semibold text-sx-ink1">Revisar foto</h2>
          {DirectionSelector}

          {processing && <p className="text-sx-ink3">Procesando…</p>}

          {!processing && reviewUrl && (
            <img src={reviewUrl} alt="Foto capturada" className="w-full rounded-lg border border-sx-line" />
          )}

          {captureState.wasBlurry && (
            <p
              role="alert"
              className="rounded-lg border px-3 py-2 text-sm"
              style={{ borderColor: '#fbd38d', background: '#fffaf0', color: '#c05621' }}
            >
              La foto puede salir borrosa. Puedes usarla igual o repetirla.
            </p>
          )}

          {role === 'tenant_admin' && (
            <label className="flex flex-col text-sm text-sx-ink2">
              Empresa
              <select
                value={companyId}
                onChange={(e) => setCompanyId(e.target.value)}
                className="rounded-md border border-sx-line bg-white px-2 py-1.5 text-sx-ink1"
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
            <p
              role="alert"
              className="rounded-lg border px-3 py-2 text-sm"
              style={{ borderColor: '#feb2b2', background: '#fff5f5', color: '#9b2c2c' }}
            >
              {uploadState.message}
            </p>
          )}

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={handleRetake}
              className="rounded-md border border-sx-line bg-white px-4 py-2 font-medium text-sx-ink2"
            >
              Repetir
            </button>
            <button
              type="button"
              onClick={handleUseThisPhoto}
              disabled={!canUpload || processing}
              className="flex-1 rounded-md bg-gradient-to-br from-sx-brand to-sx-brand2 px-4 py-2 font-semibold text-white disabled:opacity-40"
            >
              {upload.isPending ? 'Subiendo…' : 'Usar esta foto'}
            </button>
            {uploadState.retryable && uploadState.message && (
              <button
                type="button"
                onClick={handleUseThisPhoto}
                className="rounded-md border border-sx-line bg-white px-4 py-2 text-sx-ink2"
              >
                Reintentar
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="mx-auto w-[90%] max-w-[600px] py-6">
      <div
        className="space-y-4 rounded-xl border-t-4 bg-gradient-to-b from-[#fafafa] via-[#f5f5f5] to-[#f0f0f0] p-5 text-sx-ink1 shadow-[0_8px_30px_rgba(0,0,0,.15)]"
        style={{ borderTopColor: cardBorderColor }}
      >
        {Header}
        {CompanyChip}
        {DirectionSelector}

        {captureError && (
          <p
            role="alert"
            className="rounded-lg border px-3 py-2 text-sm"
            style={{ borderColor: '#feb2b2', background: '#fff5f5', color: '#9b2c2c' }}
          >
            {captureError}
          </p>
        )}

        {camera.status === 'requesting' && <p className="text-sx-ink3">Pidiendo acceso a la cámara…</p>}

        {camera.status === 'active' && (
          <div className="space-y-3">
            <div className="rounded-lg border-4 p-1" style={{ borderColor: `${cardBorderColor}66` }}>
              <video ref={videoRef} autoPlay playsInline muted className="w-full rounded" />
            </div>
            <button
              type="button"
              onClick={() => void handleManualCapture()}
              className="w-full rounded-full bg-gradient-to-br from-sx-brand to-sx-brand2 px-4 py-3 font-semibold text-white shadow-md"
            >
              📷 Capturar
            </button>
          </div>
        )}

        {camera.status === 'unavailable' && (
          <div className="space-y-3">
            <p className="text-sx-ink3">
              No se pudo acceder a la cámara. Elige o toma una foto con tu dispositivo.
            </p>
            <input
              type="file"
              aria-label="Elige o toma una foto"
              accept="image/*"
              capture="environment"
              onChange={(e) => void handleFileSelected(e)}
              className="text-sm text-sx-ink2"
            />
          </div>
        )}

        <p className="text-right text-xs">
          <Link to={ROUTES.history} className="text-sx-brand underline">
            📋 Historial de facturas
          </Link>
        </p>
      </div>
    </div>
  )
}

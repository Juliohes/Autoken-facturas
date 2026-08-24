// Captura directa S6.11: la persona decide dirección y empresa antes de abrir la
// cámara. Tras disparar, normaliza y sube sin una revisión que interrumpa el flujo.
import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { Link, useLocation } from 'react-router-dom'

import { ROUTES } from '../../app/routes'
import { useCompanyOptions } from '../companies/useCompanyOptions'
import { useSession } from '../session/SessionProvider'
import { analyzeFrame } from './analyzeFrame'
import { resolveEffectiveCompanyId } from './captureSelectors'
import { acquireCaptureLock, DEFAULT_SHARPNESS_THRESHOLD, releaseCaptureLock } from './captureLoop'
import { DocumentOverlay } from './DocumentOverlay'
import { CapturePreview, type CapturePreviewStatus } from './CapturePreview'
import { acceptContinuousUpload, createContinuousCaptureState, hasReachedContinuousLimit, type ContinuousCaptureState } from './continuousCapture'
import { grabVideoFrame } from './grabVideoFrame'
import { fileToJpegBlob } from './normalizeToJpeg'
import { processCapturedFrame } from './processCapture'
import type { CaptureProductMode, Direction } from './types'
import { useCameraStream } from './useCameraStream'
import { useScannerEngine } from './useScannerEngine'
import { useUploadBatchCapture, useUploadCapture, type AcceptedUpload } from './useUploadCapture'

interface Props {
  /** `lowSharpness` (S6.14 C8): aviso informativo de una sola vez para la pantalla de confirmación,
   * nunca un bloqueo. Reutiliza el mismo umbral ya calibrado en `captureLoop.ts`. */
  onUploaded: (fileId: string, direction: Direction, lowSharpness: boolean) => void
}

interface CapturedPage {
  id: number
  blob: Blob
  previewUrl: string
}

interface CapturedPreview {
  blob: Blob
  previewUrl: string
  sharpnessScore: number | null
  companyId: string
  direction: Direction
}

function pageGuidance(pageIndex: number) {
  if (pageIndex === 0) return 'Página 1: datos fiscales'
  if (pageIndex === 1) return 'Página 2: importes'
  return `Página ${pageIndex + 1}: datos complementarios`
}

function previewUrlFor(blob: Blob) {
  return typeof URL.createObjectURL === 'function' ? URL.createObjectURL(blob) : ''
}

function releasePreviewUrl(url: string) {
  if (url && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(url)
}

function firstVideoTrack(stream: MediaStream | null) {
  if (!stream) return undefined
  return stream.getVideoTracks?.()[0] ?? stream.getTracks()[0]
}

function newContinuousSessionId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16)
    const value = character === 'x' ? random : (random & 0x3) | 0x8
    return value.toString(16)
  })
}

export function CaptureScreen({ onUploaded }: Props) {
  const { user } = useSession()
  const role = user?.role
  const continuousCaptureEnabled = user?.feature_flags?.continuous_capture_enabled !== false
  const scannerV2Enabled = user?.feature_flags?.scanner_v2_enabled !== false
  // S6.14 C7: mensaje de una sola vez cuando se llega aquí redirigido tras una "captura ilegible"
  // (`ConfirmationScreen.tsx`), vía estado de navegación efímero (mismo patrón que `lowSharpness`).
  const location = useLocation()
  const redirectMessage = (location.state as { message?: string } | null)?.message ?? null
  const camera = useCameraStream()
  const videoRef = useRef<HTMLVideoElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Invalida resultados tardíos de una cámara o selección anterior antes de que
  // puedan iniciar una subida distinta de la última decisión consciente.
  const operationRef = useRef(0)
  const pagesRef = useRef<CapturedPage[]>([])
  const nextPageIdRef = useRef(0)
  const addingPageRef = useRef(false)
  const captureLockRef = useRef(false)
  const [direction, setDirection] = useState<Direction>('recibida')
  const [companyId, setCompanyId] = useState('')
  const [processing, setProcessing] = useState(false)
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [videoReady, setVideoReady] = useState(false)
  const [multiplePages, setMultiplePages] = useState(false)
  const [productMode, setProductMode] = useState<CaptureProductMode>('single_invoice')
  const [continuousSession, setContinuousSession] = useState<ContinuousCaptureState>(() => createContinuousCaptureState(newContinuousSessionId()))
  const [continuousNotice, setContinuousNotice] = useState<string | null>(null)
  const [pages, setPages] = useState<CapturedPage[]>([])
  const [capturedPreview, setCapturedPreview] = useState<CapturedPreview | null>(null)
  const [previewStatus, setPreviewStatus] = useState<CapturePreviewStatus>('idle')
  const [addingPage, setAddingPage] = useState(false)
  const [torchOn, setTorchOn] = useState(false)
  const companies = useCompanyOptions({ enabled: role === 'tenant_admin' })
  const upload = useUploadCapture()
  const uploadBatch = useUploadBatchCapture()
  const effectiveCompanyId = resolveEffectiveCompanyId(role, user?.company?.id, companyId)
  const canStart = effectiveCompanyId !== '' && !processing && !captureLockRef.current

  // El análisis continuo acompaña el encuadre, pero nunca sustituye la decisión manual de disparar.
  const { analysis: liveAnalysis } = useScannerEngine(videoRef.current, { enabled: scannerV2Enabled && videoReady })

  useEffect(() => {
    setVideoReady(false)
    if (videoRef.current) videoRef.current.srcObject = camera.stream
  }, [camera.stream])

  useEffect(() => {
    pagesRef.current = pages
  }, [pages])

  useEffect(() => {
    return () => {
      if (capturedPreview) releasePreviewUrl(capturedPreview.previewUrl)
    }
  }, [capturedPreview])

  useEffect(() => {
    return () => {
      operationRef.current += 1
      pagesRef.current.forEach((page) => releasePreviewUrl(page.previewUrl))
    }
  }, [])

  const markVideoReady = () => {
    const video = videoRef.current
    setVideoReady(Boolean(video && video.videoWidth > 0 && video.videoHeight > 0))
  }

  const uploadBlob = async (
    blob: Blob,
    operation: number,
    sharpnessScore: number | null,
    targetCompanyId = effectiveCompanyId,
    targetDirection = direction,
    captureSessionId?: string,
    captureSequence?: number,
  ): Promise<AcceptedUpload | null> => {
    // Aviso no bloqueante (S6.14 C8): un análisis ausente (p. ej. selector de archivo, sin cámara)
    // no cuenta como "baja nitidez" — solo se avisa cuando SÍ hay una puntuación y es baja.
    try {
      const data = await upload.mutateAsync({
        blob,
        companyId: targetCompanyId,
        direction: targetDirection,
        sharpnessScore,
        captureSessionId,
        captureSequence,
      })
      if (operationRef.current !== operation) return null
      return data
    } catch {
      if (operationRef.current === operation) setCaptureError('No se pudo subir la foto. Inténtalo de nuevo.')
      return null
    } finally {
      if (operationRef.current === operation) setProcessing(false)
    }
  }

  const addPage = (blob: Blob): boolean => {
    const current = pagesRef.current
    if (current.length >= 5) {
      setCaptureError('Ya has añadido el máximo de cinco páginas.')
      return false
    }
    nextPageIdRef.current += 1
    const next = [...current, { id: nextPageIdRef.current, blob, previewUrl: previewUrlFor(blob) }]
    pagesRef.current = next
    setPages(next)
    return true
  }

  const stopTorch = async () => {
    const track = firstVideoTrack(camera.stream)
    if (!torchOn || !track?.applyConstraints) return
    try {
      await track.applyConstraints({ advanced: [{ torch: false } as MediaTrackConstraintSet] })
    } catch {
      // Apagar la luz es una limpieza de recursos: un fallo no debe impedir cerrar la cámara.
    } finally {
      setTorchOn(false)
    }
  }

  const stopCamera = () => {
    void stopTorch()
    camera.close()
  }

  const closeCamera = () => {
    operationRef.current += 1
    addingPageRef.current = false
    setAddingPage(false)
    stopCamera()
    setCaptureError(null)
  }

  const handleManualCapture = async () => {
    if (!canStart) return
    if (multiplePages && (addingPageRef.current || pagesRef.current.length >= 5)) {
      if (pagesRef.current.length >= 5) {
        setCaptureError('Ya has añadido el máximo de cinco páginas.')
        stopCamera()
      }
      return
    }
    if (!acquireCaptureLock(captureLockRef)) return
    const frame = await grabVideoFrame(videoRef.current as HTMLVideoElement)
    if (!frame) {
      releaseCaptureLock(captureLockRef)
      setVideoReady(false)
      setCaptureError('La cámara aún no está lista. Inténtalo de nuevo.')
      if (multiplePages) stopCamera()
      return
    }
    const operation = operationRef.current + 1
    operationRef.current = operation
    setCaptureError(null)
    if (!multiplePages) setProcessing(true)
    if (multiplePages) {
      addingPageRef.current = true
      setAddingPage(true)
    }
    // El frame ya está en memoria: no se necesita mantener cámara ni linterna mientras OpenCV
    // normaliza la imagen. Evita dejar recursos del móvil activos ante un procesado lento.
    stopCamera()
    try {
      const analysis = scannerV2Enabled ? await analyzeFrame(frame) : null
      if (operationRef.current !== operation) return
      const blob = await processCapturedFrame(frame, analysis?.corners ?? null)
      if (operationRef.current !== operation) return
      if (multiplePages) {
        addPage(blob)
      } else {
        setCapturedPreview({
          blob,
          previewUrl: previewUrlFor(blob),
          sharpnessScore: analysis?.sharpness ?? null,
          companyId: effectiveCompanyId,
          direction,
        })
        setPreviewStatus('idle')
      }
    } catch {
      if (operationRef.current === operation) {
        setCaptureError('No se pudo preparar la foto. Inténtalo de nuevo.')
        // La cámara multipágina se cerró justo tras capturar el frame, antes de normalizarlo.
        if (!multiplePages) setProcessing(false)
      }
    } finally {
      releaseCaptureLock(captureLockRef)
      if (!multiplePages && operationRef.current === operation) setProcessing(false)
      if (multiplePages && operationRef.current === operation) {
        addingPageRef.current = false
        setAddingPage(false)
      }
    }
  }

  const handleFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (files.length === 0 || !canStart) return
    if (multiplePages) {
      if (addingPageRef.current) return
      const available = 5 - pagesRef.current.length
      if (available <= 0) {
        setCaptureError('Ya has añadido el máximo de cinco páginas.')
        return
      }
      const operation = operationRef.current + 1
      operationRef.current = operation
      addingPageRef.current = true
      setAddingPage(true)
      setCaptureError(null)
      try {
        const normalized = await Promise.all(files.slice(0, available).map((file) => fileToJpegBlob(file)))
        if (operationRef.current !== operation) return
        normalized.forEach(addPage)
        if (files.length > available) setCaptureError('Solo se pueden añadir cinco páginas por factura.')
        stopCamera()
      } catch {
        if (operationRef.current === operation) {
          setCaptureError('No se pudo preparar una de las fotos. Elige imágenes válidas.')
          stopCamera()
        }
      } finally {
        if (operationRef.current === operation) {
          addingPageRef.current = false
          setAddingPage(false)
        }
      }
      return
    }
    const [file] = files
    if (!acquireCaptureLock(captureLockRef)) return
    const operation = operationRef.current + 1
    operationRef.current = operation
    setCaptureError(null)
    setProcessing(true)
    stopCamera()
    try {
      const blob = await fileToJpegBlob(file)
      if (operationRef.current !== operation) return
      setCapturedPreview({
        blob,
        previewUrl: previewUrlFor(blob),
        sharpnessScore: null,
        companyId: effectiveCompanyId,
        direction,
      })
      setPreviewStatus('idle')
    } catch {
      if (operationRef.current === operation) {
        setCaptureError('No se pudo preparar la foto. Elige otra imagen.')
        setProcessing(false)
      }
    } finally {
      releaseCaptureLock(captureLockRef)
      if (operationRef.current === operation) setProcessing(false)
    }
  }

  const repeatPreview = () => {
    if (!capturedPreview || processing) return
    operationRef.current += 1
    setCapturedPreview(null)
    setPreviewStatus('idle')
    setCaptureError(null)
    setVideoReady(false)
    setMultiplePages(false)
    camera.open()
  }

  const confirmPreview = async () => {
    if (!capturedPreview || processing || !acquireCaptureLock(captureLockRef)) return
    const preview = capturedPreview
    const operation = operationRef.current + 1
    operationRef.current = operation
    setCaptureError(null)
    setPreviewStatus('uploading')
    setProcessing(true)
    const uploaded = await uploadBlob(
      preview.blob,
      operation,
      preview.sharpnessScore,
      preview.companyId,
      preview.direction,
      productMode === 'continuous_invoices' ? continuousSession.sessionId : undefined,
      productMode === 'continuous_invoices' ? continuousSession.currentSequence + 1 : undefined,
    )
    releaseCaptureLock(captureLockRef)
    if (uploaded && operationRef.current === operation) {
      if (productMode === 'continuous_invoices') {
        const accepted = acceptContinuousUpload(continuousSession, uploaded.id)
        setContinuousSession(accepted.state)
        setContinuousNotice(uploaded.duplicate ? 'Esta factura ya estaba subida.' : `Factura ${accepted.state.currentSequence} guardada.`)
        setCapturedPreview(null)
        setPreviewStatus('idle')
        if (!hasReachedContinuousLimit(accepted.state)) {
          setVideoReady(false)
          camera.open()
        }
      } else {
        setPreviewStatus('saved')
        const lowSharpness = preview.sharpnessScore !== null && preview.sharpnessScore < DEFAULT_SHARPNESS_THRESHOLD
        onUploaded(uploaded.id, preview.direction, lowSharpness)
      }
    } else if (operationRef.current === operation) setPreviewStatus('idle')
  }

  const openCamera = (forMultiplePages = false) => {
    if (!canStart) {
      setCaptureError('Elige una empresa antes de tomar la foto.')
      return
    }
    setCaptureError(null)
    setProductMode(forMultiplePages ? 'multipage_invoice' : 'single_invoice')
    setMultiplePages(forMultiplePages)
    camera.open()
  }

  const openFilePicker = () => {
    if (!canStart) {
      setCaptureError('Elige una empresa antes de subir la foto.')
      return
    }
    fileInputRef.current?.click()
  }

  const startContinuousCapture = () => {
    if (!continuousCaptureEnabled) return
    if (!canStart) {
      setCaptureError('Elige una empresa antes de tomar las fotos.')
      return
    }
    setCaptureError(null)
    setContinuousNotice(null)
    setProductMode('continuous_invoices')
    setContinuousSession(createContinuousCaptureState(newContinuousSessionId()))
    setMultiplePages(false)
    camera.open()
  }

  const finishContinuousCapture = () => {
    setProductMode('single_invoice')
    setMultiplePages(false)
    stopCamera()
  }

  const startMultiplePages = () => {
    if (!continuousCaptureEnabled) return
    if (!canStart) {
      setCaptureError('Elige una empresa antes de añadir las fotos.')
      return
    }
    setCaptureError(null)
    setProductMode('multipage_invoice')
    setMultiplePages(true)
    camera.open()
  }

  const removePage = (index: number) => {
    const page = pagesRef.current[index]
    if (!page) return
    releasePreviewUrl(page.previewUrl)
    const next = pagesRef.current.filter((_, currentIndex) => currentIndex !== index)
    pagesRef.current = next
    setPages(next)
  }

  const sendPages = async () => {
    if (pages.length < 2 || processing) return
    const operation = operationRef.current + 1
    operationRef.current = operation
    setCaptureError(null)
    setProcessing(true)
    stopCamera()
    try {
      const data = await uploadBatch.mutateAsync({
        blobs: pages.map((page) => page.blob),
        companyId: effectiveCompanyId,
        direction,
      })
      // Decisión de diseño (S6.14 C8): una factura de varias páginas no tiene una única nitidez de
      // conjunto (cada página se capturó/normalizó por separado, sin acumular su análisis); en vez
      // de inventar un agregado, este camino nunca avisa de baja nitidez.
      if (operationRef.current === operation) onUploaded(data.id, direction, false)
    } catch {
      if (operationRef.current === operation) setCaptureError('No se pudo enviar la factura. Inténtalo de nuevo.')
    } finally {
      if (operationRef.current === operation) setProcessing(false)
    }
  }

  const videoTrack = firstVideoTrack(camera.stream)
  const capabilities = videoTrack && 'getCapabilities' in videoTrack
    ? (videoTrack.getCapabilities() as MediaTrackCapabilities)
    : undefined
  const torchAvailable = Boolean((capabilities as { torch?: boolean } | undefined)?.torch && videoTrack?.applyConstraints)

  const toggleTorch = async () => {
    if (!videoTrack?.applyConstraints || !torchAvailable) return
    const next = !torchOn
    try {
      await videoTrack.applyConstraints({ advanced: [{ torch: next } as MediaTrackConstraintSet] })
      setTorchOn(next)
    } catch {
      setTorchOn(false)
    }
  }

  if (role === 'user' && !user?.company) {
    return <p role="alert" className="p-6 text-red-400">No se pudo cargar tu empresa. Inténtalo de nuevo más tarde.</p>
  }

  const directionButtonClass = 'cursor-pointer rounded-full border border-slate-600 px-6 py-3 text-base font-medium text-slate-200 has-[:checked]:border-emerald-500 has-[:checked]:bg-emerald-600 has-[:checked]:text-white'
  const DirectionSelector = (
    <fieldset className="flex gap-3 text-sm text-slate-200">
      <legend className="sr-only">Dirección</legend>
      <label className={directionButtonClass}>
        <input type="radio" name="direction" className="sr-only" checked={direction === 'recibida'} onChange={() => setDirection('recibida')} />
        Recibida
      </label>
      <label className={directionButtonClass}>
        <input type="radio" name="direction" className="sr-only" checked={direction === 'emitida'} onChange={() => setDirection('emitida')} />
        Emitida
      </label>
    </fieldset>
  )

  if (capturedPreview) {
    return (
      <CapturePreview
        previewUrl={capturedPreview.previewUrl}
        status={previewStatus}
        error={captureError}
        onRepeat={repeatPreview}
        onUse={() => void confirmPreview()}
      />
    )
  }

  if (processing) {
    return (
      <section className="mx-auto flex max-w-xl flex-col items-center gap-4 p-6 pt-20 text-slate-100">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-700 border-t-emerald-500" />
        <p className="font-medium">Procesando factura...</p>
      </section>
    )
  }

  return (
    <section className="mx-auto max-w-xl space-y-5 p-6 text-slate-100">
      {DirectionSelector}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Capturar factura</h1>
        <Link to={ROUTES.history} className="rounded-md border border-emerald-600 px-3 py-1.5 text-sm font-medium text-emerald-400 hover:bg-emerald-600/10">Ver historial</Link>
      </div>
      {role === 'tenant_admin' && (
        <label className="flex flex-col text-sm text-slate-300">
          Empresa
          <select value={companyId} onChange={(event) => setCompanyId(event.target.value)} className="rounded border border-slate-600 bg-slate-800 px-2 py-1">
            <option value="">Elige una empresa</option>
            {(companies.data ?? []).map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
          </select>
        </label>
      )}
      {redirectMessage && (
        <p data-testid="capture-redirect-message" className="rounded-md border border-amber-500/60 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          {redirectMessage}
        </p>
      )}
      {captureError && <p role="alert" className="text-sm text-red-400">{captureError}</p>}
      {continuousNotice && <p role="status" className="text-sm text-emerald-300">{continuousNotice}</p>}

      {productMode === 'continuous_invoices' && continuousSession.accepted.length > 0 && (
        <section aria-label="Sesión de varias facturas" className="space-y-3 rounded-lg border border-emerald-700/60 bg-emerald-950/20 p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="font-medium">{continuousSession.accepted.length} de {continuousSession.maxItems} facturas aceptadas</p>
            <button type="button" onClick={finishContinuousCapture} className="rounded-md border border-slate-600 px-3 py-2 text-sm">Terminar sesión</button>
          </div>
          <ol className="flex flex-wrap gap-2">
            {continuousSession.accepted.map((invoice) => (
              <li key={invoice.fileId} aria-label={`Factura ${invoice.sequence}`} className="rounded border border-emerald-800 px-3 py-1 text-sm text-emerald-200">
                Factura {invoice.sequence} aceptada
              </li>
            ))}
          </ol>
        </section>
      )}

      {camera.status === 'idle' && (
        <div className="space-y-5">
          <div className="flex justify-center">
            <button type="button" onClick={() => openCamera()} className="h-36 w-36 rounded-full bg-emerald-600 text-lg font-semibold text-white shadow-lg shadow-emerald-950/40 hover:bg-emerald-500">Tomar foto</button>
          </div>
          <div className="flex justify-center gap-3">
            <button type="button" onClick={openFilePicker} className="rounded-md border border-slate-600 px-4 py-3 text-base font-medium text-slate-100">Subir archivo</button>
            {continuousCaptureEnabled && <button type="button" onClick={startContinuousCapture} className="rounded-md border border-emerald-600 px-4 py-3 text-base font-medium text-emerald-300">Varias facturas</button>}
            {continuousCaptureEnabled && <button type="button" onClick={startMultiplePages} className="rounded-md border border-slate-600 px-4 py-3 text-base font-medium text-slate-100">Varias hojas</button>}
          </div>
        </div>
      )}

      {multiplePages && pages.length > 0 && camera.status === 'idle' && (
        <MultiPagePanel pages={pages} onRemove={removePage} onAdd={() => openCamera(true)} onSelectFiles={openFilePicker} onSend={() => void sendPages()} />
      )}

      {camera.status !== 'idle' && (
        <div role="dialog" aria-modal="true" aria-label="Cámara para capturar factura" className="fixed inset-0 z-50 flex min-h-screen flex-col bg-slate-950 p-0 text-slate-100">
          <div className="relative flex min-h-screen flex-1 flex-col justify-end">
            {camera.status === 'requesting' && <p className="text-center text-slate-300">Pidiendo acceso a la cámara…</p>}
            {camera.status === 'active' && (
              <>
                <video ref={videoRef} autoPlay playsInline muted onLoadedData={markVideoReady} onLoadedMetadata={markVideoReady} className="absolute inset-0 h-full w-full object-cover" />
                <div data-testid="camera-guide-frame" aria-hidden="true" className="pointer-events-none absolute inset-4 rounded border-4 border-emerald-400 shadow-[0_0_0_9999px_rgb(0_0_0_/_0.35)]" />
                <DocumentOverlay
                  corners={liveAnalysis?.corners ?? null}
                  sourceWidth={videoRef.current?.videoWidth ?? 0}
                  sourceHeight={videoRef.current?.videoHeight ?? 0}
                  state={liveAnalysis?.corners ? liveAnalysis.detectionConfidence !== undefined && liveAnalysis.detectionConfidence >= 0.75 && (liveAnalysis.areaRatio ?? 0) >= 0.3 ? 'good' : 'detected' : 'none'}
                />
                {multiplePages && <p className="absolute left-4 right-4 top-[max(1rem,env(safe-area-inset-top))] rounded bg-slate-950/80 px-3 py-2 text-center text-sm font-medium">{pageGuidance(pages.length)}</p>}
                {productMode === 'continuous_invoices' && <p className="absolute left-4 right-4 top-[max(1rem,env(safe-area-inset-top))] rounded bg-slate-950/80 px-3 py-2 text-center text-sm font-medium">Factura {continuousSession.currentSequence + 1} de {continuousSession.maxItems}</p>}
                {torchAvailable && <button type="button" aria-label="Linterna" onClick={() => void toggleTorch()} className="absolute right-4 top-[max(1rem,env(safe-area-inset-top))] rounded-full bg-slate-950/80 px-4 py-2 text-sm font-medium">Linterna{torchOn ? ' encendida' : ''}</button>}
              </>
            )}
            {camera.status === 'unavailable' && <p className="text-slate-400">{camera.unavailableReason === 'insecure' ? 'La cámara requiere una conexión segura. Puedes subir una foto desde tu dispositivo.' : 'No se pudo acceder a la cámara. Puedes subir una foto desde tu dispositivo.'}</p>}
            <div className="relative z-10 flex w-full flex-wrap gap-3 bg-gradient-to-t from-slate-950 via-slate-950/90 to-transparent px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-12">
              {camera.status === 'active' && <button type="button" onClick={() => void handleManualCapture()} disabled={!videoReady || addingPage} className="flex-1 rounded-md bg-emerald-600 px-4 py-4 text-lg font-semibold text-white disabled:opacity-40">{addingPage ? 'Añadiendo página…' : videoReady ? 'Capturar foto' : 'Preparando cámara…'}</button>}
              {camera.status === 'active' && !videoReady && camera.canRetry && <button type="button" onClick={camera.retry} className="rounded-md border border-slate-600 px-4 py-3 font-medium">Reintentar cámara</button>}
              {camera.status !== 'active' && camera.canRetry && <button type="button" onClick={camera.retry} className="rounded-md border border-slate-600 px-4 py-3 font-medium">Reintentar cámara</button>}
              <button type="button" onClick={openFilePicker} className="rounded-md border border-slate-600 bg-slate-950/70 px-4 py-3 font-medium">Subir archivo</button>
              <button type="button" onClick={closeCamera} className="rounded-md border border-slate-600 px-4 py-3 font-medium">Cerrar cámara</button>
            </div>
          </div>
        </div>
      )}
      <input ref={fileInputRef} type="file" aria-label="Elige o toma una foto" accept="image/*" multiple={multiplePages && continuousCaptureEnabled} onChange={(event) => void handleFileSelected(event)} className="sr-only" />
    </section>
  )
}

function MultiPagePanel({ pages, onRemove, onAdd, onSelectFiles, onSend }: {
  pages: CapturedPage[]
  onRemove: (index: number) => void
  onAdd: () => void
  onSelectFiles: () => void
  onSend: () => void
}) {
  return (
    <section aria-label="Páginas de la factura" className="space-y-3 rounded-lg border border-slate-700 p-4">
      <p className="text-sm text-slate-300">{pages.length < 2 ? 'Añade la página de importes para poder enviar.' : pages.length < 5 ? 'Puedes añadir datos complementarios si hacen falta.' : 'Has añadido el máximo de cinco páginas.'}</p>
      <ol className="flex flex-wrap gap-3">
        {pages.map((page, index) => (
          <li key={page.id} aria-label={`${pageGuidance(index)} ${index + 1}`} className="relative w-20">
            <img src={page.previewUrl} alt={`Miniatura página ${index + 1}`} className="h-24 w-20 rounded object-cover" />
            <button type="button" onClick={() => onRemove(index)} className="mt-1 text-xs text-red-300">Quitar página {index + 1}</button>
          </li>
        ))}
      </ol>
      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={onAdd} disabled={pages.length >= 5} className="rounded-md border border-slate-600 px-3 py-2 text-sm disabled:opacity-40">Tomar otra foto</button>
        <button type="button" onClick={onSelectFiles} disabled={pages.length >= 5} className="rounded-md border border-slate-600 px-3 py-2 text-sm disabled:opacity-40">Añadir desde archivo</button>
        <button type="button" onClick={onSend} disabled={pages.length < 2} className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40">Enviar factura</button>
      </div>
    </section>
  )
}

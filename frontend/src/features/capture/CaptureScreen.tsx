// Captura directa S6.11: la persona decide dirección y empresa antes de abrir la
// cámara. Tras disparar, normaliza y sube sin una revisión que interrumpa el flujo.
import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { createPortal } from 'react-dom'
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
import { loadOpenCv } from './opencv/loadOpenCv'
import { startCaptureTiming } from './capturePerformance'
import { Modal } from '../../shared/Modal'
import type { CaptureProductMode, Direction } from './types'
import { useAutoCapture } from './useAutoCapture'
import { useCameraStream } from './useCameraStream'
import { useScannerEngine } from './useScannerEngine'
import { useUploadBatchCapture, useUploadCapture, type AcceptedUpload } from './useUploadCapture'
import { useInvoiceInbox } from '../inbox/useInvoiceInbox'

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
  const autoCaptureHandlerRef = useRef<() => boolean | Promise<boolean>>(() => false)
  const [direction, setDirection] = useState<Direction | null>(role === 'tenant_admin' ? 'recibida' : null)
  const [companyId, setCompanyId] = useState('')
  const [processing, setProcessing] = useState(false)
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const [videoReady, setVideoReady] = useState(false)
  const [multiplePages, setMultiplePages] = useState(false)
  const [productMode, setProductMode] = useState<CaptureProductMode>('single_invoice')
  const [continuousSession, setContinuousSession] = useState<ContinuousCaptureState>(() => createContinuousCaptureState(newContinuousSessionId()))
  const [continuousNotice, setContinuousNotice] = useState<string | null>(null)
  const [pages, setPages] = useState<CapturedPage[]>([])
  const [capturedPreview, setCapturedPreview] = useState<CapturedPreview | null>(null)
  const [duplicateUploadId, setDuplicateUploadId] = useState<string | null>(null)
  const [previewStatus, setPreviewStatus] = useState<CapturePreviewStatus>('idle')
  const [addingPage, setAddingPage] = useState(false)
  const [captureInProgress, setCaptureInProgress] = useState(false)
  const [torchOn, setTorchOn] = useState(false)
  const companies = useCompanyOptions({ enabled: role === 'tenant_admin' })
  const upload = useUploadCapture()
  const uploadBatch = useUploadBatchCapture()
  const inbox = useInvoiceInbox(null, user?.feature_flags?.review_inbox_enabled !== false)
  const effectiveCompanyId = resolveEffectiveCompanyId(role, user?.company?.id, companyId)
  const actionable = (inbox.data?.summary?.ready ?? 0) + (inbox.data?.summary?.attention ?? 0)
  const canStart = direction !== null && effectiveCompanyId !== '' && !processing && !captureInProgress && !captureLockRef.current
  const blockedAction = (message: string) => {
    if (actionable >= 10) {
      setCaptureError(null)
      setTooManyPending(true)
      return
    }
    setCaptureError(message)
  }
  const [tooManyPending, setTooManyPending] = useState(false)

  // Precalienta OpenCV mientras el usuario encuadra para que la primera captura no pague la carga
  // del runtime WASM después de pulsar el disparador.
  useEffect(() => {
    if (camera.status === 'active') void loadOpenCv().catch(() => undefined)
  }, [camera.status])

  // El análisis continuo arma AUTO solo cuando todas las señales y la estabilidad cumplen el gate;
  // MANUAL sigue disponible como decisión consciente de la persona.
  const scannerEnabled = scannerV2Enabled && videoReady && camera.status === 'active'
    && !capturedPreview && !processing && !captureInProgress && !addingPage
  const { analysis: liveAnalysis } = useScannerEngine(videoRef.current, { enabled: scannerEnabled })
  const scanner = useAutoCapture({
    analysis: liveAnalysis,
    enabled: scannerEnabled,
    sourceWidth: videoRef.current?.videoWidth ?? 0,
    sourceHeight: videoRef.current?.videoHeight ?? 0,
    onAutoCapture: () => autoCaptureHandlerRef.current(),
  })

  useEffect(() => {
    setVideoReady(false)
    const video = videoRef.current
    if (!video) return
    video.srcObject = camera.stream
    if (!camera.stream) return

    const startPlayback = () => {
      const playback = video.play?.()
      if (playback) void playback.catch(() => undefined)
    }
    video.addEventListener('loadedmetadata', startPlayback)
    video.addEventListener('canplay', startPlayback)
    startPlayback()
    return () => {
      video.removeEventListener('loadedmetadata', startPlayback)
      video.removeEventListener('canplay', startPlayback)
    }
  }, [camera.stream, capturedPreview])

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
    targetDirection = direction as Direction,
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

  const resumeContinuousCamera = () => {
    const track = firstVideoTrack(camera.stream)
    const streamIsLive = camera.status === 'active'
      && camera.stream !== null
      && (!track || track.readyState === 'live')
    setVideoReady(false)
    if (!streamIsLive) camera.open()
  }

  const closeCamera = () => {
    operationRef.current += 1
    addingPageRef.current = false
    setAddingPage(false)
    scanner.reset()
    stopCamera()
    setCaptureError(null)
  }
  const closeCameraRef = useRef(closeCamera)
  closeCameraRef.current = closeCamera

  useEffect(() => {
    if (camera.status === 'idle') return undefined
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeCameraRef.current()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [camera.status])

  const handleManualCapture = async (): Promise<boolean> => {
    if (!canStart || capturedPreview || processing) return false
    if (multiplePages && (addingPageRef.current || pagesRef.current.length >= 5)) {
      if (pagesRef.current.length >= 5) {
        setCaptureError('Ya has añadido el máximo de cinco páginas.')
        stopCamera()
      }
      return false
    }
    if (!acquireCaptureLock(captureLockRef)) return false
    scanner.markManualCaptureStarted()
    setCaptureInProgress(true)
    const timing = startCaptureTiming()
    const operation = operationRef.current + 1
    operationRef.current = operation
    setCaptureError(null)
    try {
      const frame = await grabVideoFrame(videoRef.current as HTMLVideoElement)
      if (!frame) {
        setVideoReady(false)
        setCaptureError('La cámara aún no está lista. Inténtalo de nuevo.')
        stopCamera()
        return true
      }
      timing.mark('frame')
      setCaptureError(null)
      if (!multiplePages) setProcessing(true)
      if (multiplePages) {
        addingPageRef.current = true
        setAddingPage(true)
      }
      // En simple y multipágina se liberan recursos mientras se procesa; continuous conserva el stream
      // para volver a encuadrar sin pedir permiso ni abrir otra cámara después del 201.
      if (productMode !== 'continuous_invoices') stopCamera()
      let analysis = null
      if (scannerV2Enabled) {
        try {
          analysis = await analyzeFrame(frame)
        } catch {
          // El análisis mejora el recorte y el aviso de nitidez, pero nunca debe descartar la foto.
        }
      }
      timing.mark('analysis')
      if (operationRef.current !== operation) return true
      const blob = await processCapturedFrame(frame, analysis?.corners ?? null)
      timing.mark('processing')
      if (operationRef.current !== operation) return true
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
        timing.mark('preview')
      }
    } catch {
      if (operationRef.current === operation) {
        setCaptureError('No se pudo preparar la foto. Inténtalo de nuevo.')
        if (productMode === 'continuous_invoices') stopCamera()
        if (!multiplePages) setProcessing(false)
      }
    } finally {
      releaseCaptureLock(captureLockRef)
      scanner.notifyCaptureFinished()
      setCaptureInProgress(false)
      if (!multiplePages && operationRef.current === operation) setProcessing(false)
      if (multiplePages && operationRef.current === operation) {
        addingPageRef.current = false
        setAddingPage(false)
      }
    }
    return true
  }

  autoCaptureHandlerRef.current = () => handleManualCapture()

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
      if (!acquireCaptureLock(captureLockRef)) return
      const operation = operationRef.current + 1
      operationRef.current = operation
      setCaptureInProgress(true)
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
        releaseCaptureLock(captureLockRef)
        setCaptureInProgress(false)
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
    setCaptureInProgress(true)
    setCaptureError(null)
    setProcessing(true)
    if (productMode !== 'continuous_invoices') stopCamera()
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
      setCaptureInProgress(false)
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
    if (productMode === 'continuous_invoices') resumeContinuousCamera()
    else camera.open()
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
        if (uploaded.duplicate) {
          setContinuousNotice('Esta factura ya estaba subida. No se ha creado una nueva.')
          stopCamera()
        } else {
          setCapturedPreview(null)
          setPreviewStatus('idle')
          if (!hasReachedContinuousLimit(accepted.state)) {
            resumeContinuousCamera()
          } else {
            stopCamera()
          }
        }
      } else {
        if (uploaded.duplicate) {
          setDuplicateUploadId(uploaded.id)
          setPreviewStatus('idle')
        } else {
          setPreviewStatus('saved')
          const lowSharpness = preview.sharpnessScore !== null && preview.sharpnessScore < DEFAULT_SHARPNESS_THRESHOLD
          onUploaded(uploaded.id, preview.direction, lowSharpness)
          setCapturedPreview(null)
          setDirection(null)
          setSuccessMessage('Factura subida correctamente. Queda pendiente de OCR.')
        }
      }
    } else if (operationRef.current === operation) setPreviewStatus('idle')
  }

  const openCamera = (forMultiplePages = false) => {
    if (!canStart) {
      blockedAction(direction ? 'Elige una empresa antes de tomar la foto.' : 'Elige la dirección antes de tomar la foto.')
      return
    }
    setCaptureError(null)
    setProductMode(forMultiplePages ? 'multipage_invoice' : 'single_invoice')
    setMultiplePages(forMultiplePages)
    camera.open()
  }

  const openFilePicker = () => {
    if (!canStart) {
      blockedAction(direction ? 'Elige una empresa antes de subir la foto.' : 'Elige la dirección antes de subir la foto.')
      return
    }
    fileInputRef.current?.click()
  }

  const startContinuousCapture = () => {
    if (!continuousCaptureEnabled) return
    if (!canStart) {
      blockedAction(direction ? 'Elige una empresa antes de tomar las fotos.' : 'Elige la dirección antes de tomar las fotos.')
      return
    }
    setCaptureError(null)
    setContinuousNotice(null)
    setProductMode('continuous_invoices')
    setContinuousSession(createContinuousCaptureState(newContinuousSessionId()))
    setMultiplePages(false)
    camera.open()
  }
  void startContinuousCapture

  const finishContinuousCapture = () => {
    setProductMode('single_invoice')
    setMultiplePages(false)
    stopCamera()
  }

  const startMultiplePages = () => {
    if (multiplePages && camera.status === 'idle' && pagesRef.current.length === 0) {
      setProductMode('single_invoice')
      setMultiplePages(false)
      setCaptureError(null)
      return
    }
    if (!canStart) {
      blockedAction(direction ? 'Elige una empresa antes de añadir las fotos.' : 'Elige la dirección antes de añadir las fotos.')
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
    if (pages.length < 2 || processing || !direction) return
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
      if (operationRef.current === operation && direction) {
        onUploaded(data.id, direction, false)
        setDirection(null)
        pagesRef.current.forEach((page) => releasePreviewUrl(page.previewUrl))
        setPages([])
        pagesRef.current = []
        setMultiplePages(false)
        setSuccessMessage('Factura subida correctamente. Queda pendiente de OCR.')
      }
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
    return <p role="alert" className="tn-panel-page p-6 text-red-400">No se pudo cargar tu empresa. Inténtalo de nuevo más tarde.</p>
  }

  const directionButtonClass = 'tn-toggle-option cursor-pointer border px-6 py-3 text-base font-medium'
  const DirectionSelector = (
    <fieldset className="tn-direction-toggle flex gap-1 text-sm">
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

  const autoCaptureReason: Record<string, string> = {
    no_document: 'Encuadra la factura dentro de la guía.',
    low_confidence: 'Ajusta el encuadre para detectar mejor la factura.',
    too_small: 'Acércate un poco más a la factura.',
    clipped: 'Aleja la factura del borde de la guía.',
    blurry: 'Mantén el móvil quieto para enfocar.',
    too_dark: 'Busca más luz sobre la factura.',
    too_bright: 'Evita los reflejos directos sobre la factura.',
    perspective_extreme: 'Coloca el móvil más paralelo a la factura.',
    moving: 'Mantén la factura estable…',
    ready: 'Factura lista. Capturando…',
  }
  const documentOverlayState = !liveAnalysis?.corners
    ? 'none'
    : scanner.phase === 'auto_armed'
      ? 'auto_armed'
      : scanner.phase === 'stabilizing'
        ? 'stabilizing'
        : scanner.decision.ready ? 'good' : 'detected'

  if (capturedPreview) {
    return (
      <>
        <CapturePreview
          previewUrl={capturedPreview.previewUrl}
          status={previewStatus}
          error={captureError}
          onRepeat={repeatPreview}
          onUse={() => void confirmPreview()}
        />
        {duplicateUploadId && (
          <Modal title="Factura duplicada" onClose={() => setDuplicateUploadId(null)} panelClassName="max-w-md space-y-4">
            <p className="text-slate-300">Esta factura ya estaba subida. No se ha creado una nueva.</p>
            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => {
                  setDuplicateUploadId(null)
                  repeatPreview()
                }}
                className="rounded-md border border-slate-600 px-4 py-2"
              >
                Repetir foto
              </button>
              <Link
                to={ROUTES.confirmation(duplicateUploadId)}
                onClick={() => setDuplicateUploadId(null)}
                className="rounded-md bg-emerald-600 px-4 py-2 text-center font-semibold"
              >
                Revisar factura original
              </Link>
            </div>
          </Modal>
        )}
      </>
    )
  }

  if (processing) {
    return (
      <section className="tn-panel-page mx-auto flex max-w-xl flex-col items-center gap-4 p-6 pt-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-700 border-t-emerald-500" />
        <p className="font-medium">Procesando factura...</p>
      </section>
    )
  }

  return (
    <section className="tn-panel-page tn-liquid-glass tn-capture-screen tn-capture-entry-screen mx-auto w-full max-w-none space-y-5 p-4 sm:p-6">
      {DirectionSelector}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="sr-only">Capturar factura</h1>
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
      {successMessage && <p role="status" className="rounded border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm">{successMessage}</p>}
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
          <div className="tn-capture-segmented" role="group" aria-label="Añadir factura">
            <button type="button" onClick={() => openCamera()} disabled={direction === null} className="tn-capture-segment tn-capture-segment-primary">
              <svg aria-hidden="true" className="tn-capture-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M5 8.5h3l1.5-2h5L16 8.5h3A2 2 0 0 1 21 10.5v7A2 2 0 0 1 19 19.5H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z" />
                <circle cx="12" cy="14" r="3.25" />
              </svg>
              <span>Tomar foto</span>
            </button>
            <button type="button" onClick={startMultiplePages} aria-label="Varias hojas" aria-pressed={multiplePages} disabled={direction === null} className="tn-capture-segment tn-capture-segment-secondary">
              <svg aria-hidden="true" className="tn-capture-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M8 4h9a2 2 0 0 1 2 2v11" strokeLinecap="round" />
                <path d="M6 7h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z" />
                <path d="M8 11h5M8 15h4" strokeLinecap="round" />
              </svg>
              <span>Varias<br />hojas</span>
            </button>
          </div>
          <p className="text-sm text-slate-600">Para subir documentos independientes, usa Subir Archivo.</p>
        </div>
      )}

      {multiplePages && pages.length > 0 && camera.status === 'idle' && (
        <MultiPagePanel pages={pages} onRemove={removePage} onAdd={() => openCamera(true)} onSelectFiles={openFilePicker} onSend={() => void sendPages()} />
      )}

      {camera.status !== 'idle' && createPortal(
        <div role="dialog" aria-modal="true" aria-label="Cámara para capturar factura" className="tn-capture-stage fixed inset-0 z-50 flex flex-col bg-slate-950 p-0 text-slate-100">
          <div className="tn-capture-stage-body relative min-h-0 flex-1 overflow-hidden">
            {camera.status === 'requesting' && <p className="text-center text-slate-300">Pidiendo acceso a la cámara…</p>}
            {camera.status === 'active' && (
              <>
                <video ref={videoRef} autoPlay playsInline muted onCanPlay={markVideoReady} onLoadedData={markVideoReady} onLoadedMetadata={markVideoReady} className="absolute inset-0 z-0 h-full w-full object-cover" />
                 <div data-testid="camera-guide-frame" aria-hidden="true" className="tn-camera-viewport-boundary pointer-events-none absolute inset-2 rounded" />
                <DocumentOverlay
                  corners={liveAnalysis?.corners ?? null}
                  sourceWidth={videoRef.current?.videoWidth ?? 0}
                  sourceHeight={videoRef.current?.videoHeight ?? 0}
                  state={documentOverlayState}
                />
                {multiplePages && <p className="absolute left-4 right-4 top-[max(1rem,env(safe-area-inset-top))] rounded border border-white/30 bg-slate-950/85 px-3 py-2 text-center text-sm font-medium text-white shadow-lg">{pageGuidance(pages.length)}</p>}
                {productMode === 'continuous_invoices' && <p className="absolute left-4 right-4 top-[max(1rem,env(safe-area-inset-top))] rounded border border-white/30 bg-slate-950/85 px-3 py-2 text-center text-sm font-medium text-white shadow-lg">Factura {continuousSession.currentSequence + 1} de {continuousSession.maxItems}</p>}
                {torchAvailable && (
                  <button
                    type="button"
                    aria-label={torchOn ? 'Desactivar linterna' : 'Activar linterna'}
                    aria-pressed={torchOn}
                    onClick={() => void toggleTorch()}
                    className="camera-control absolute right-4 top-[max(1rem,env(safe-area-inset-top))] inline-flex min-h-11 min-w-11 items-center justify-center rounded-full border border-white/40 bg-slate-950/80 p-2 text-white"
                  >
                    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" className="h-6 w-6">
                      <path strokeLinecap="round" strokeLinejoin="round" d="m8 8 5-5 4 4-5 5-4 4-3-3 4-4Z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="m12 12 3 3M5 19l-2 2M17 7l4-4M18 15l3 2M20 20l-3-3" />
                    </svg>
                  </button>
                )}
              </>
            )}
            {camera.status === 'unavailable' && <p className="text-slate-400">{camera.unavailableReason === 'insecure' ? 'La cámara requiere una conexión segura. Puedes subir una foto desde tu dispositivo.' : 'No se pudo acceder a la cámara. Puedes subir una foto desde tu dispositivo.'}</p>}
          </div>
          <div data-testid="camera-stage-controls" className="tn-capture-stage-controls relative z-10 flex w-full flex-wrap gap-3 bg-slate-950 px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-4">
              {camera.status === 'active' && scannerV2Enabled && (
                <div className="flex w-full flex-wrap items-center justify-between gap-3">
                  <fieldset className="camera-toolbar flex gap-2 text-sm" aria-label="Modo de captura">
                    <legend className="sr-only">Modo de captura</legend>
                    <label className="camera-mode-option cursor-pointer rounded-full border border-slate-600 px-3 py-1.5 has-[:checked]:border-emerald-500 has-[:checked]:bg-emerald-600 has-[:checked]:text-white">
                      <input
                        type="radio"
                        name="capture-mode"
                        className="sr-only"
                        checked={scanner.mode === 'auto'}
                        onChange={() => scanner.setMode('auto')}
                      />
                      Automático
                    </label>
                    <label className="camera-mode-option cursor-pointer rounded-full border border-slate-600 px-3 py-1.5 has-[:checked]:border-emerald-500 has-[:checked]:bg-emerald-600 has-[:checked]:text-white">
                      <input
                        type="radio"
                        name="capture-mode"
                        className="sr-only"
                        checked={scanner.mode === 'manual'}
                        onChange={() => scanner.setMode('manual')}
                      />
                      Manual
                    </label>
                  </fieldset>
                  {scanner.mode === 'auto' && (
                    <p role="status" className="text-right text-xs text-slate-300">
                      {autoCaptureReason[scanner.decision.reason]}
                    </p>
                  )}
                </div>
              )}
              {camera.status === 'active' && <button type="button" onClick={() => void handleManualCapture()} disabled={!videoReady || addingPage} className="camera-capture-button tn-primary-action flex-1 rounded-md px-4 py-4 text-lg font-semibold disabled:opacity-40">{addingPage ? 'Añadiendo página…' : videoReady ? 'Capturar foto' : 'Preparando cámara…'}</button>}
              {camera.status === 'active' && !videoReady && camera.canRetry && <button type="button" onClick={camera.retry} className="rounded-md border border-slate-600 px-4 py-3 font-medium">Reintentar cámara</button>}
              {camera.status !== 'active' && camera.canRetry && <button type="button" onClick={camera.retry} className="rounded-md border border-slate-600 px-4 py-3 font-medium">Reintentar cámara</button>}
              <button type="button" onClick={closeCamera} className="camera-control rounded-md border border-slate-600 px-4 py-3 font-medium">Cerrar cámara</button>
          </div>
        </div>,
        document.body,
      )}
      <input ref={fileInputRef} type="file" aria-label="Elige o toma una foto" accept="image/*" multiple={multiplePages} onChange={(event) => void handleFileSelected(event)} className="sr-only" />
      {tooManyPending && <Modal title="Revisión necesaria" onClose={() => setTooManyPending(false)} panelClassName="max-w-md space-y-4"><p>Hay demasiadas facturas pendientes de revisión. Revísalas antes de seguir.</p><Link to={ROUTES.inbox} onClick={() => setTooManyPending(false)} className="tn-primary-action inline-block rounded px-4 py-3 font-semibold">Ir a Pendientes</Link></Modal>}
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
        <button type="button" onClick={onSend} disabled={pages.length < 2} className="tn-primary-action rounded-md px-3 py-2 text-sm font-semibold disabled:opacity-40">Enviar factura</button>
      </div>
    </section>
  )
}

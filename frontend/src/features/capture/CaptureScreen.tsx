// Captura directa S6.11: la persona decide dirección y empresa antes de abrir la
// cámara. Tras disparar, normaliza y sube sin una revisión que interrumpa el flujo.
import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { Link } from 'react-router-dom'

import { ROUTES } from '../../app/routes'
import { useCompanyOptions } from '../companies/useCompanyOptions'
import { useSession } from '../session/SessionProvider'
import { analyzeFrame } from './analyzeFrame'
import { resolveEffectiveCompanyId } from './captureSelectors'
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
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Invalida resultados tardíos de una cámara o selección anterior antes de que
  // puedan iniciar una subida distinta de la última decisión consciente.
  const operationRef = useRef(0)
  const [direction, setDirection] = useState<Direction>('recibida')
  const [companyId, setCompanyId] = useState('')
  const [processing, setProcessing] = useState(false)
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [videoReady, setVideoReady] = useState(false)
  const companies = useCompanyOptions({ enabled: role === 'tenant_admin' })
  const upload = useUploadCapture()
  const effectiveCompanyId = resolveEffectiveCompanyId(role, user?.company?.id, companyId)
  const canStart = effectiveCompanyId !== '' && !processing

  useEffect(() => {
    setVideoReady(false)
    if (videoRef.current) videoRef.current.srcObject = camera.stream
  }, [camera.stream])

  useEffect(() => {
    return () => {
      operationRef.current += 1
    }
  }, [])

  const markVideoReady = () => {
    const video = videoRef.current
    setVideoReady(Boolean(video && video.videoWidth > 0 && video.videoHeight > 0))
  }

  const uploadBlob = async (blob: Blob, operation: number) => {
    try {
      const data = await upload.mutateAsync({ blob, companyId: effectiveCompanyId })
      if (operationRef.current === operation) onUploaded(data.id, direction)
    } catch {
      if (operationRef.current === operation) setCaptureError('No se pudo subir la foto. Inténtalo de nuevo.')
    } finally {
      if (operationRef.current === operation) setProcessing(false)
    }
  }

  const handleManualCapture = async () => {
    if (!canStart) return
    const frame = grabVideoFrame(videoRef.current as HTMLVideoElement)
    if (!frame) {
      setVideoReady(false)
      setCaptureError('La cámara aún no está lista. Inténtalo de nuevo.')
      return
    }
    const operation = operationRef.current + 1
    operationRef.current = operation
    setCaptureError(null)
    setProcessing(true)
    camera.close()
    try {
      const analysis = await analyzeFrame(frame)
      if (operationRef.current !== operation) return
      const blob = await processCapturedFrame(frame, analysis.corners)
      if (operationRef.current !== operation) return
      await uploadBlob(blob, operation)
    } catch {
      if (operationRef.current === operation) {
        setCaptureError('No se pudo preparar la foto. Inténtalo de nuevo.')
        setProcessing(false)
      }
    }
  }

  const handleFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || !canStart) return
    const operation = operationRef.current + 1
    operationRef.current = operation
    setCaptureError(null)
    setProcessing(true)
    camera.close()
    try {
      const blob = await fileToJpegBlob(file)
      if (operationRef.current !== operation) return
      await uploadBlob(blob, operation)
    } catch {
      if (operationRef.current === operation) {
        setCaptureError('No se pudo preparar la foto. Elige otra imagen.')
        setProcessing(false)
      }
    }
  }

  const closeCamera = () => {
    operationRef.current += 1
    camera.close()
    setCaptureError(null)
  }

  const openCamera = () => {
    if (!canStart) {
      setCaptureError('Elige una empresa antes de tomar la foto.')
      return
    }
    setCaptureError(null)
    camera.open()
  }

  const openFilePicker = () => {
    if (!canStart) {
      setCaptureError('Elige una empresa antes de subir la foto.')
      return
    }
    fileInputRef.current?.click()
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

  if (processing) {
    return (
      <section className="mx-auto flex max-w-xl flex-col items-center gap-4 p-6 pt-20 text-slate-100">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-slate-700 border-t-emerald-500" />
        <p className="font-medium">Procesando factura...</p>
      </section>
    )
  }

  return (
    <section className="mx-auto max-w-xl space-y-4 p-6 text-slate-100">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Capturar factura</h1>
        <Link to={ROUTES.history} className="rounded-md border border-emerald-600 px-3 py-1.5 text-sm font-medium text-emerald-400 hover:bg-emerald-600/10">Ver historial</Link>
      </div>
      {DirectionSelector}
      {role === 'tenant_admin' && (
        <label className="flex flex-col text-sm text-slate-300">
          Empresa
          <select value={companyId} onChange={(event) => setCompanyId(event.target.value)} className="rounded border border-slate-600 bg-slate-800 px-2 py-1">
            <option value="">Elige una empresa</option>
            {(companies.data ?? []).map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}
          </select>
        </label>
      )}
      {captureError && <p role="alert" className="text-sm text-red-400">{captureError}</p>}

      {camera.status === 'idle' && (
        <div className="flex flex-wrap gap-3">
          <button type="button" onClick={openCamera} className="rounded-md bg-emerald-600 px-4 py-3 text-base font-semibold text-white">Tomar foto</button>
          <button type="button" onClick={openFilePicker} className="rounded-md border border-slate-600 px-4 py-3 text-base font-medium text-slate-100">Subir archivo</button>
        </div>
      )}

      {camera.status !== 'idle' && (
        <div role="dialog" aria-modal="true" aria-label="Cámara para capturar factura" className="fixed inset-0 z-50 flex min-h-screen flex-col bg-slate-950 p-4 text-slate-100">
          <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-4">
            {camera.status === 'requesting' && <p className="text-center text-slate-300">Pidiendo acceso a la cámara…</p>}
            {camera.status === 'active' && (
              <div className="relative mx-auto w-full max-w-xl overflow-hidden rounded-lg bg-black">
                <video ref={videoRef} autoPlay playsInline muted onLoadedData={markVideoReady} onLoadedMetadata={markVideoReady} className="max-h-[70vh] w-full object-contain" />
                <div data-testid="camera-guide-frame" aria-hidden="true" className="pointer-events-none absolute left-1/2 top-1/2 h-[72vh] max-w-[78vw] -translate-x-1/2 -translate-y-1/2 aspect-[1/1.414] rounded border-4 border-emerald-400 shadow-[0_0_0_9999px_rgb(0_0_0_/_0.35)]" />
              </div>
            )}
            {camera.status === 'unavailable' && <p className="text-slate-400">{camera.unavailableReason === 'insecure' ? 'La cámara requiere una conexión segura. Puedes subir una foto desde tu dispositivo.' : 'No se pudo acceder a la cámara. Puedes subir una foto desde tu dispositivo.'}</p>}
            <div className="mx-auto flex w-full max-w-xl flex-wrap gap-3">
              {camera.status === 'active' && <button type="button" onClick={() => void handleManualCapture()} disabled={!videoReady} className="flex-1 rounded-md bg-emerald-600 px-4 py-4 text-lg font-semibold text-white disabled:opacity-40">{videoReady ? 'Capturar foto' : 'Preparando cámara…'}</button>}
              {camera.status === 'active' && !videoReady && camera.canRetry && <button type="button" onClick={camera.retry} className="rounded-md border border-slate-600 px-4 py-3 font-medium">Reintentar cámara</button>}
              {camera.status !== 'active' && camera.canRetry && <button type="button" onClick={camera.retry} className="rounded-md border border-slate-600 px-4 py-3 font-medium">Reintentar cámara</button>}
              <button type="button" onClick={openFilePicker} className="rounded-md border border-slate-600 px-4 py-3 font-medium">Subir archivo</button>
              <button type="button" onClick={closeCamera} className="rounded-md border border-slate-600 px-4 py-3 font-medium">Cerrar cámara</button>
            </div>
          </div>
        </div>
      )}
      <input ref={fileInputRef} type="file" aria-label="Elige o toma una foto" accept="image/*" onChange={(event) => void handleFileSelected(event)} className="sr-only" />
    </section>
  )
}

import { useRef, useState, type ChangeEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { ROUTES } from '../../app/routes'
import { Modal } from '../../shared/Modal'
import { Banner, SegmentedControl } from '../../ui'
import { useSession } from '../session/SessionProvider'
import { useInvoiceInbox } from '../inbox/useInvoiceInbox'
import { useUploadCapture } from '../capture/useUploadCapture'
import type { Direction } from '../capture/types'

const MAX_FILES = 10

export function UploadFileScreen() {
  const { user } = useSession()
  const navigate = useNavigate()
  const inputRef = useRef<HTMLInputElement>(null)
  const [direction, setDirection] = useState<Direction | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [showLimit, setShowLimit] = useState(false)
  const upload = useUploadCapture()
  const inbox = useInvoiceInbox(null, user?.feature_flags?.review_inbox_enabled !== false)
  const companyId = user?.company?.id ?? ''
  const actionable = (inbox.data?.summary?.ready ?? 0) + (inbox.data?.summary?.attention ?? 0)

  const openPicker = () => {
    if (actionable >= 10) {
      setShowLimit(true)
      return
    }
    if (!direction) {
      setMessage('Elige si la factura es recibida o emitida antes de subirla.')
      return
    }
    if (!companyId) {
      setMessage('No se pudo cargar tu empresa. Inténtalo de nuevo más tarde.')
      return
    }
    inputRef.current?.click()
  }

  const selectFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    if (files.length === 0) return
    if (files.length > MAX_FILES) {
      setMessage('Puedes seleccionar como máximo 10 documentos.')
      return
    }
    if (!direction || !companyId) return
    setBusy(true)
    setMessage(null)
    const results = await Promise.allSettled(files.map((file) => upload.mutateAsync({
      blob: file,
      companyId,
      direction,
    })))
    const failedResults = results.flatMap((result, index) => result.status === 'rejected' ? [{ name: files[index].name }] : [])
    const failed = failedResults.length
    setBusy(false)
    setDirection(null)
    if (failed === 0) setMessage(`${files.length} ${files.length === 1 ? 'factura subida' : 'facturas subidas'} correctamente.`)
    else if (failed === files.length) setMessage(`No se pudo subir ningún documento (${failedResults.map((item) => item.name).join(', ')}).`)
    else setMessage(`${files.length - failed} documentos subidos. No se pudieron subir: ${failedResults.map((item) => item.name).join(', ')}.`)
  }

  return (
    <section className="tn-panel-page mx-auto w-full max-w-2xl space-y-6 p-6" aria-labelledby="upload-title">
      <div>
        <h1 id="upload-title" className="text-2xl font-semibold">Subir Archivo</h1>
        <p className="mt-1 text-slate-600">Cada imagen o PDF se enviará como una factura independiente.</p>
      </div>
      <SegmentedControl
        label="Dirección de la factura"
        value={direction}
        onChange={setDirection}
        options={[{ value: 'recibida', label: 'Recibida' }, { value: 'emitida', label: 'Emitida' }]}
      />
      {message && <Banner tone="info">{message}</Banner>}
      <button type="button" onClick={openPicker} disabled={busy} className="tn-primary-action min-h-11 rounded px-5 py-3 font-semibold disabled:opacity-50">
        {busy ? 'Subiendo documentos...' : 'Elegir imágenes o PDF'}
      </button>
      <input ref={inputRef} type="file" accept="application/pdf,image/*" multiple onChange={(event) => void selectFiles(event)} className="sr-only" aria-label="Elegir imágenes o PDF" />
      {showLimit && (
        <Modal title="Revisión necesaria" onClose={() => setShowLimit(false)} panelClassName="max-w-md space-y-4">
          <p>Hay demasiadas facturas pendientes de revisión. Revísalas antes de seguir.</p>
          <button type="button" className="tn-primary-action rounded px-4 py-3 font-semibold" onClick={() => navigate(ROUTES.inbox)}>Ir a Pendientes</button>
        </Modal>
      )}
    </section>
  )
}

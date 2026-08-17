// El historial refleja envíos aceptados, incluso mientras el OCR está pendiente o ha fallado.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { postJson } from '../../api/client'
import { ROUTES } from '../../app/routes'
import { useInvoiceHistory } from './useInvoiceHistory'
import type { HistoryEntry } from './types'

const STATUS_LABEL: Record<string, string> = {
  pending_ocr: 'Pendiente de OCR',
  processing: 'Procesando OCR',
  ocr_done: 'Lista para revisar',
  ocr_failed: 'OCR no completado',
  needs_review: 'Pendiente de comprobación',
  confirmed: 'Confirmada',
}

export function InvoiceHistory() {
  const history = useInvoiceHistory()

  if (history.isLoading) {
    return <p className="p-6 text-slate-400">Cargando…</p>
  }

  if (history.isError) {
    return (
      <p role="alert" className="p-6 text-red-400">
        No se pudo cargar el historial. Inténtalo de nuevo.
      </p>
    )
  }

  // La API ya ordena y acota; el corte visual evita que una respuesta degradada muestre más de los
  // veinte envíos que define S6.12.
  const entries = (history.data?.entries ?? []).slice(0, 20)

  if (entries.length === 0) {
    return <p className="p-6 text-slate-400">Todavía no has enviado ninguna factura.</p>
  }

  return (
    <section className="mx-auto max-w-2xl space-y-4 p-6 text-slate-100">
      <h1 className="text-xl font-semibold">Historial de facturas</h1>
      <ul className="divide-y divide-slate-700" data-testid="history-list">
        {entries.map((entry) => (
          <HistoryRow key={entry.id} entry={entry} />
        ))}
      </ul>
    </section>
  )
}

function HistoryRow({ entry }: { entry: HistoryEntry }) {
  const queryClient = useQueryClient()
  const retryOcr = useMutation({
    mutationFn: async () => {
      const response = await postJson(`/api/v1/uploads/${entry.id}/retry-ocr`)
      if (!response.ok) throw new Error('No se pudo reintentar la lectura')
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['invoice-history'] })
    },
  })
  const reviewState = entry.status === 'ocr_done' || entry.status === 'needs_review'
  const pendingState = entry.status === 'pending_ocr' || entry.status === 'processing'
  const confirmationState = entry.direction === undefined ? undefined : { direction: entry.direction }

  return (
    <li data-testid="history-row" className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="font-medium">Factura enviada</p>
        <time dateTime={entry.created_at} className="text-sm text-slate-400">{formatCreatedAt(entry.created_at)}</time>
      </div>
      <div className="shrink-0 space-y-1 text-right text-sm text-slate-400">
        <p>{STATUS_LABEL[entry.status] ?? entry.status}</p>
        {pendingState && <Link to={ROUTES.confirmation(entry.id)} state={confirmationState} className="text-emerald-400">Ver progreso</Link>}
        {reviewState && <Link to={ROUTES.confirmation(entry.id)} state={confirmationState} className="text-emerald-400">Revisar factura</Link>}
        {entry.status === 'ocr_failed' && (
          <button type="button" onClick={() => retryOcr.mutate()} disabled={retryOcr.isPending} className="text-emerald-400 disabled:opacity-40">
            {retryOcr.isPending ? 'Reintentando lectura…' : 'Reintentar lectura'}
          </button>
        )}
        {retryOcr.isError && <p role="alert" className="text-red-400">No se pudo reintentar la lectura.</p>}
      </div>
    </li>
  )
}

function formatCreatedAt(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('es-ES')
}

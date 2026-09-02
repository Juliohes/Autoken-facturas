import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { ROUTES } from '../../app/routes'
import { Modal } from '../../shared/Modal'
import { StatusBadge, type StatusTone } from '../../ui'
import { INBOX_QUERY_KEY } from './useInvoiceInbox'
import { useDeleteUpload } from '../confirmation/useDeleteUpload'
import type { InboxItem as InboxItemData } from './types'

// capture_unreadable no aparece aquí (paso 9, ajustes UI): InvoiceInbox lo filtra antes de
// renderizar ningún InboxItem, así que este componente no necesita conocer ese estado.
const STATUS_LABEL: Record<string, string> = {
  pending_ocr: 'En cola',
  processing: 'Procesando OCR',
  ocr_done: 'Lista para revisar',
  needs_review: 'Pendiente de comprobación',
  ocr_failed: 'OCR no completado',
  confirmed: 'Confirmada',
}

// Tono semántico por estado (color + icono + texto, AA). El estado nunca es solo color.
const STATUS_TONE: Record<string, StatusTone> = {
  pending_ocr: 'neutral',
  processing: 'info',
  ocr_done: 'ok',
  needs_review: 'warn',
  ocr_failed: 'bad',
  confirmed: 'ok',
}

export function InboxItem({ item }: { item: InboxItemData }) {
  const queryClient = useQueryClient()
  const deleteUpload = useDeleteUpload(item.id)
  const [showDeleteDialog, setShowDeleteDialog] = useState(false)
  const confirmationState = item.direction === null ? undefined : { direction: item.direction }
  const pending = item.status === 'pending_ocr' || item.status === 'processing'
  const reviewable = item.status === 'ocr_done' || item.status === 'needs_review'

  return (
    <li className="tn-inbox-item flex items-center justify-between gap-4" data-testid="inbox-item">
      <div className="min-w-0">
        <p className="font-medium text-slate-100">Factura enviada</p>
        <p className="text-sm text-muted flex items-center gap-2">
          <StatusBadge plain tone={STATUS_TONE[item.status] ?? 'neutral'} label={STATUS_LABEL[item.status] ?? item.status} />
        </p>
        <time dateTime={item.created_at} className="text-xs text-slate-500">
          {formatCreatedAt(item.created_at)}
        </time>
      </div>
      <div className="shrink-0 flex items-center gap-3">
        {pending && <Link to={ROUTES.confirmation(item.id)} state={confirmationState} className="tn-inbox-action tn-inbox-action-neutral">Ver progreso</Link>}
        {reviewable && <Link to={ROUTES.confirmation(item.id)} state={confirmationState} className="tn-inbox-action tn-inbox-action-success">Revisar factura</Link>}
        {item.status !== 'confirmed' && (
          <button
            type="button"
            onClick={() => setShowDeleteDialog(true)}
            className="tn-inbox-action tn-inbox-action-danger"
          >
            Eliminar
          </button>
        )}
      </div>
      {showDeleteDialog && (
        <Modal title="Eliminar factura" onClose={() => setShowDeleteDialog(false)} panelClassName="max-w-md space-y-4">
          <p className="text-slate-300">Esta factura no se ha confirmado ni guardado. ¿Quieres eliminarla para hacerla de nuevo?</p>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setShowDeleteDialog(false)} className="rounded-md border border-slate-600 px-4 py-2">Cancelar</button>
            <button
              type="button"
              disabled={deleteUpload.isPending}
              onClick={() => deleteUpload.mutate(undefined, {
                onSuccess: async () => {
                  setShowDeleteDialog(false)
                  await queryClient.invalidateQueries({ queryKey: INBOX_QUERY_KEY })
                },
              })}
              className="rounded-md bg-red-600 px-4 py-2 font-semibold disabled:opacity-40"
            >
              {deleteUpload.isPending ? 'Eliminando...' : 'Sí, eliminar'}
            </button>
          </div>
          {deleteUpload.isError && <p role="alert" className="text-sm text-red-400">No se pudo eliminar la factura.</p>}
        </Modal>
      )}
    </li>
  )
}

// Sin segundos (bloque E, PROMPT-AUTOFACTU-AJUSTES-v3): dateStyle/timeStyle 'short' no los incluye,
// a diferencia de toLocaleString('es-ES') por defecto.
function formatCreatedAt(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('es-ES', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

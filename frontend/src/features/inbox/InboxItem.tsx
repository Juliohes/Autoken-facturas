import { Link } from 'react-router-dom'

import { ROUTES } from '../../app/routes'
import type { InboxItem as InboxItemData } from './types'

const STATUS_LABEL: Record<string, string> = {
  pending_ocr: 'En cola',
  processing: 'Procesando OCR',
  ocr_done: 'Lista para revisar',
  needs_review: 'Pendiente de comprobación',
  ocr_failed: 'OCR no completado',
  capture_unreadable: 'Foto ilegible',
  confirmed: 'Confirmada',
}

export function InboxItem({ item }: { item: InboxItemData }) {
  const confirmationState = item.direction === null ? undefined : { direction: item.direction }
  const pending = item.status === 'pending_ocr' || item.status === 'processing'
  const reviewable = item.status === 'ocr_done' || item.status === 'needs_review'

  return (
    <li className="flex items-center justify-between gap-4 border-b border-slate-700 py-4" data-testid="inbox-item">
      <div className="min-w-0">
        <p className="font-medium text-slate-100">Factura enviada</p>
        <p className="text-sm text-slate-400">
          {STATUS_LABEL[item.status] ?? item.status} · {item.page_count} {item.page_count === 1 ? 'página' : 'páginas'}
        </p>
        <time dateTime={item.created_at} className="text-xs text-slate-500">
          {formatCreatedAt(item.created_at)}
        </time>
      </div>
      <div className="shrink-0 text-right">
        {pending && <Link to={ROUTES.confirmation(item.id)} state={confirmationState} className="text-sm text-emerald-400">Ver progreso</Link>}
        {reviewable && <Link to={ROUTES.confirmation(item.id)} state={confirmationState} className="text-sm text-emerald-400">Revisar factura</Link>}
        {item.status === 'capture_unreadable' && <Link to={ROUTES.capture} className="text-sm text-emerald-400">Repetir foto</Link>}
      </div>
    </li>
  )
}

function formatCreatedAt(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('es-ES')
}

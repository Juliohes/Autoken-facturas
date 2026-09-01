// El historial (R-056 C9) muestra solo facturas ya confirmadas de los últimos 4 meses, en modo
// solo lectura. `STATUS_LABEL`/`STATUS_TONE` cubren igualmente los estados heredados por si el
// backend degradase la respuesta: el filtro de abajo nunca deja pasar otra cosa que 'confirmed'.
import { useState } from 'react'

import { Banner, EmptyState, Spinner, StatusBadge, type StatusTone } from '../../ui'
import { useInvoiceHistory } from './useInvoiceHistory'
import type { HistoryEntry } from './types'

const STATUS_LABEL: Record<string, string> = {
  pending_ocr: 'Pendiente de OCR',
  processing: 'Procesando OCR',
  ocr_done: 'Lista para revisar',
  ocr_failed: 'OCR no completado',
  needs_review: 'Pendiente de comprobación',
  confirmed: 'Confirmada',
  // S6.14 C7: estado propio, distinguible de "pendiente de revisión" y de "fallo de OCR" — no
  // admite reintentar leer la MISMA imagen (a diferencia de `ocr_failed`), solo repetir la foto.
  capture_unreadable: 'No se pudo leer, repite la foto',
}

// Tono semántico por estado (color + icono + texto, AA). Solo 'confirmed' llega hoy a esta lista.
const STATUS_TONE: Record<string, StatusTone> = {
  pending_ocr: 'neutral',
  processing: 'info',
  ocr_done: 'ok',
  ocr_failed: 'bad',
  needs_review: 'warn',
  confirmed: 'ok',
  capture_unreadable: 'bad',
}

export function InvoiceHistory() {
  const [cursor, setCursor] = useState<string | null>(null)
  const history = useInvoiceHistory(cursor)

  if (history.isLoading) {
    return (
      <section className="tn-panel-page mx-auto flex max-w-2xl items-center justify-center p-6">
        <Spinner label="Cargando…" />
      </section>
    )
  }

  if (history.isError) {
    return (
      <section className="tn-panel-page mx-auto max-w-2xl p-6">
        <Banner tone="bad">No se pudo cargar el historial. Inténtalo de nuevo.</Banner>
      </section>
    )
  }

  // La API ya ordena y acota; el corte visual evita que una respuesta degradada muestre más de los
  // veinte envíos que define S6.12.
  // R-056 C9: solo facturas confirmadas, máximo 20 por página como capa defensiva frontend.
  const entries = (history.data?.entries ?? []).filter((entry) => entry.status === 'confirmed').slice(0, 20)

  if (entries.length === 0 && cursor === null) {
    return (
      <section className="tn-panel-page mx-auto max-w-2xl space-y-4 p-6">
        <h1 className="text-xl font-semibold">Historial</h1>
        <EmptyState title="Todavía no tienes facturas confirmadas en los últimos cuatro meses." />
      </section>
    )
  }

  return (
    <section className="tn-panel-page mx-auto max-w-2xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Historial de facturas</h1>
      <ul className="divide-y divide-line" data-testid="history-list">
        {entries.map((entry) => (
          <HistoryRow key={entry.id} entry={entry} />
        ))}
      </ul>
      {history.data?.next_cursor && (
        <button
          type="button"
          onClick={() => setCursor(history.data?.next_cursor ?? null)}
          disabled={history.isFetching}
          className="tn-btn tn-btn-secondary tn-btn-md"
        >
          {history.isFetching ? 'Cargando…' : 'Cargar más'}
        </button>
      )}
    </section>
  )
}

function HistoryRow({ entry }: { entry: HistoryEntry }) {
  return (
    <li data-testid="history-row" className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="font-medium">Factura enviada</p>
        <time dateTime={entry.created_at} className="text-sm text-muted">{formatCreatedAt(entry.created_at)}</time>
      </div>
      <div className="shrink-0 space-y-1 text-right text-sm text-muted">
        <StatusBadge tone={STATUS_TONE[entry.status] ?? 'neutral'} label={STATUS_LABEL[entry.status] ?? entry.status} />
        <p className="text-xs">Solo lectura</p>
      </div>
    </li>
  )
}

function formatCreatedAt(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('es-ES')
}

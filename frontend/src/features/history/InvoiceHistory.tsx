// El historial (R-056 C9) muestra solo facturas ya confirmadas de los últimos 4 meses, en modo
// solo lectura. `STATUS_LABEL`/`STATUS_TONE` cubren igualmente los estados heredados por si el
// backend degradase la respuesta: el filtro de abajo nunca deja pasar otra cosa que 'confirmed'.
import { useState } from 'react'

import { Banner, EmptyState, Spinner, StatusBadge, type StatusTone } from '../../ui'
import { useInvoiceHistory } from './useInvoiceHistory'
import type { HistoryEntry, HistoryPeriod } from './types'

const PERIOD_OPTIONS: ReadonlyArray<{ value: HistoryPeriod; label: string }> = [
  { value: 'total', label: 'Total' },
  { value: 'month', label: 'Este mes' },
  { value: 'quarter', label: 'Este trimestre' },
  { value: 'year', label: 'Este año' },
]

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
  const [period, setPeriod] = useState<HistoryPeriod>('total')
  const history = useInvoiceHistory(cursor, period)

  // Cambiar de periodo empieza una lista nueva: un cursor de otro periodo no significa nada aquí.
  const changePeriod = (next: HistoryPeriod) => {
    setPeriod(next)
    setCursor(null)
  }

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

  const count = history.data?.count ?? 0

  if (entries.length === 0 && cursor === null) {
    return (
      <section className="tn-panel-page mx-auto max-w-2xl space-y-4 p-6">
        <h1 className="text-xl font-semibold">Historial</h1>
        <PeriodFilter period={period} count={count} onChange={changePeriod} />
        <EmptyState title="Todavía no tienes facturas confirmadas en los últimos cuatro meses." />
      </section>
    )
  }

  return (
    <section className="tn-panel-page mx-auto max-w-2xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Historial de facturas</h1>
      <PeriodFilter period={period} count={count} onChange={changePeriod} />
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

function PeriodFilter({ period, count, onChange }: { period: HistoryPeriod; count: number; onChange: (period: HistoryPeriod) => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <label className="flex items-center gap-2 text-sm font-medium">
        Periodo
        <select
          className="tn-select"
          value={period}
          onChange={(event) => onChange(event.target.value as HistoryPeriod)}
        >
          {PERIOD_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
      </label>
      <p className="text-sm text-muted">{count} {count === 1 ? 'factura' : 'facturas'}</p>
    </div>
  )
}

function HistoryRow({ entry }: { entry: HistoryEntry }) {
  // Fallback sin inventar (bloque D, ajustes v3): si el backend no manda el dato, texto neutro.
  const title = entry.invoice_number ? `Factura Nº ${entry.invoice_number}` : 'Sin número'
  const invoiceDateLabel = entry.invoice_date ? `Fecha factura: ${formatInvoiceDate(entry.invoice_date)}` : 'Sin fecha'
  return (
    <li data-testid="history-row" className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="font-medium">{title}</p>
        <p className="text-sm text-muted">{invoiceDateLabel}</p>
        <time dateTime={entry.created_at} className="text-xs text-muted">Subida: {formatCreatedAt(entry.created_at)}</time>
      </div>
      <div className="shrink-0 space-y-1 text-right text-sm text-muted">
        <StatusBadge tone={STATUS_TONE[entry.status] ?? 'neutral'} label={STATUS_LABEL[entry.status] ?? entry.status} />
      </div>
    </li>
  )
}

// invoice_date llega como "AAAA-MM-DD" (sin hora ni zona): reconstruir el string a mano evita el
// desfase de un día que da `new Date('AAAA-MM-DD')` en husos horarios detrás de UTC.
function formatInvoiceDate(value: string): string {
  const [year, month, day] = value.split('-')
  if (!year || !month || !day) return value
  return `${day}/${month}/${year}`
}

// Sin segundos (bloque E, PROMPT-AUTOFACTU-AJUSTES-v3): dateStyle/timeStyle 'short' no los incluye,
// a diferencia de toLocaleString('es-ES') por defecto.
function formatCreatedAt(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('es-ES', { dateStyle: 'short', timeStyle: 'short' }).format(date)
}

// Pantalla de historial (S2.6): lista de solo lectura de las facturas confirmadas
// de los últimos 7 días del usuario, la más reciente primero. Orquesta el hook de
// datos y la presentación de cada fila; sin lógica de negocio aquí (vive en el
// backend, que ya filtra/ordena/acota). Comportamientos C7-C9 de la spec.
import { useInvoiceHistory } from './useInvoiceHistory'
import type { HistoryEntry } from './types'

const DIRECTION_LABEL: Record<string, string> = {
  recibida: 'Recibida',
  emitida: 'Emitida',
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

  const entries = history.data?.entries ?? []

  if (entries.length === 0) {
    return <p className="p-6 text-slate-400">No hay facturas en los últimos 7 días.</p>
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
  return (
    <li data-testid="history-row" className="flex items-center justify-between py-3">
      <div>
        <p className="font-medium">{entry.counterparty_name ?? '—'}</p>
        <p className="text-sm text-slate-400">
          {entry.issue_date ?? '—'} · {DIRECTION_LABEL[entry.direction] ?? entry.direction}
        </p>
      </div>
      <div className="text-right">
        <p className="font-semibold">{entry.total_amount ?? '—'}</p>
        <p className="text-sm text-slate-400">{entry.counterparty_cif_status}</p>
      </div>
    </li>
  )
}

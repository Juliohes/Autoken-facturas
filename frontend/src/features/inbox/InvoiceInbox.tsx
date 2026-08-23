import { useEffect, useState } from 'react'

import { InboxItem } from './InboxItem'
import { useInvoiceInbox } from './useInvoiceInbox'
import type { InboxItem as InboxItemData } from './types'
import { useSession } from '../session/SessionProvider'

export function InvoiceInbox() {
  const { user } = useSession()
  const [cursor, setCursor] = useState<string | null>(null)
  const [items, setItems] = useState<InboxItemData[]>([])
  const inbox = useInvoiceInbox(cursor, user?.feature_flags?.review_inbox_enabled !== false)

  useEffect(() => {
    if (!inbox.data) return
    setItems((current) => {
      if (cursor === null) return inbox.data.items
      const byId = new Map(current.map((item) => [item.id, item]))
      for (const item of inbox.data.items) byId.set(item.id, item)
      return Array.from(byId.values())
    })
  }, [cursor, inbox.data])

  if (user?.feature_flags?.review_inbox_enabled === false) {
    return <p className="p-6 text-slate-400">La bandeja está temporalmente desactivada.</p>
  }

  if (inbox.isLoading && items.length === 0) {
    return <p className="p-6 text-slate-400">Cargando tus facturas...</p>
  }

  if (inbox.isError && items.length === 0) {
    return <p role="alert" className="p-6 text-red-400">No se pudo cargar tu bandeja. Inténtalo de nuevo.</p>
  }

  const summary = inbox.data?.summary ?? { processing: 0, ready: 0, attention: 0 }
  const hasMore = inbox.data?.next_cursor !== null && inbox.data?.next_cursor !== undefined

  return (
    <section className="mx-auto max-w-2xl space-y-5 p-6 text-slate-100">
      <div>
        <h1 className="text-xl font-semibold">Mis facturas</h1>
        <p className="mt-1 text-sm text-slate-400">Solo aparecen las facturas que has subido tú.</p>
      </div>
      <div className="grid grid-cols-3 gap-2" aria-label="Resumen de facturas">
        <SummaryCard label="Procesando" value={summary.processing} />
        <SummaryCard label="Listas" value={summary.ready} />
        <SummaryCard label="Revisar" value={summary.attention} />
      </div>
      {items.length === 0 ? (
        <p className="text-slate-400">Todavía no has enviado ninguna factura.</p>
      ) : (
        <ul data-testid="inbox-list">
          {items.map((item) => <InboxItem key={item.id} item={item} />)}
        </ul>
      )}
      {hasMore && (
        <button
          type="button"
          className="rounded-md border border-slate-600 px-4 py-2 text-sm text-slate-200 disabled:opacity-50"
          disabled={inbox.isFetching}
          onClick={() => setCursor(inbox.data?.next_cursor ?? null)}
        >
          {inbox.isFetching ? 'Cargando...' : 'Cargar más'}
        </button>
      )}
    </section>
  )
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-slate-700 bg-slate-800/50 px-3 py-2 text-center">
      <p className="text-lg font-semibold text-emerald-300">{value}</p>
      <p className="text-xs text-slate-400">{label}</p>
    </div>
  )
}

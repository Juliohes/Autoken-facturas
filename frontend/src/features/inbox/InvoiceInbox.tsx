import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'

import { InboxItem } from './InboxItem'
import { useInvoiceInbox } from './useInvoiceInbox'
import type { InboxItem as InboxItemData } from './types'
import { useSession } from '../session/SessionProvider'

export function InvoiceInbox() {
  const { user } = useSession()
  const location = useLocation()
  const [cursor, setCursor] = useState<string | null>(null)
  const [items, setItems] = useState<InboxItemData[]>([])
  const inbox = useInvoiceInbox(cursor, user?.feature_flags?.review_inbox_enabled !== false)

  useEffect(() => {
    if (!inbox.data) return
    // Defensa (paso 9, ajustes UI): una captura ilegible ni se ha leído, no es "pendiente de
    // comprobación". El backend ya la excluye; esto es solo el respaldo si llegara igualmente.
    const readable = inbox.data.items.filter((item) => item.status !== 'capture_unreadable')
    setItems((current) => {
      if (cursor === null) return readable
      const byId = new Map(current.map((item) => [item.id, item]))
      for (const item of readable) byId.set(item.id, item)
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
    <section className="tn-panel-page tn-scroll-clear-bottom-nav mx-auto max-w-2xl space-y-5 p-6">
      <div>
        <h1 className="text-xl font-semibold">Pendientes</h1>
        <p className="mt-1 text-sm text-muted">Solo aparecen las facturas que has subido tú.</p>
      </div>
      {(location.state as { message?: string } | null)?.message && (
        <p role="status" className="rounded-md border border-emerald-500/60 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
          {(location.state as { message: string }).message}
        </p>
      )}
      <div className="grid grid-cols-2 gap-2" aria-label="Resumen de facturas">
        <SummaryCard label="Procesando" value={summary.processing} />
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
    <div className="tn-summary-card rounded-md border px-3 py-2 text-center">
      {/* Bloque 8 (a11y): sin `text-emerald-300` -- el remapeo legacy `.tn-panel-page
          .text-emerald-300` (verde oscuro, para superficies claras) pisaba por especificidad
          a `.tn-summary-card p:first-child` (acento sobre esta tarjeta glass oscura),
          dejando el número con ~2.17:1 de contraste. Sin esa clase, aplica el color pensado
          para esta superficie. */}
      <p className="text-lg font-semibold">{value}</p>
      <p className="text-xs text-muted">{label}</p>
    </div>
  )
}

// Pantalla de historial (S2.6): lista de solo lectura de las facturas confirmadas
// de los últimos 7 días del usuario, la más reciente primero. Orquesta el hook de
// datos y la presentación de cada fila; sin lógica de negocio aquí (vive en el
// backend, que ya filtra/ordena/acota). Comportamientos C7-C9 de la spec.
//
// Experimento 2026-08-01 (rama experiment/setex-user-ui-v1): el rol `user` ve la anatomía de
// HIPERDOC-FRONTEND-USUARIO-v1-setex1.md §13 (tabla clara, filas alternadas, distintivo NIF/NIE/
// CIF); `tenant_admin` sigue viendo la pantalla oscura de siempre — esta pantalla es compartida
// por los dos roles (`ROUTE_DEFS`), así que decide su propio aspecto según quién la mira.
import { Link } from 'react-router-dom'

import { ROUTES } from '../../app/routes'
import { formatCurrency, formatDate } from '../../shared/format'
import { SetexBadge } from '../../shared/SetexBadge'
import { setexTaxIdKind, TAX_ID_LABEL } from '../../shared/setexTaxIdKind'
import { useSession } from '../session/SessionProvider'
import { useInvoiceHistory } from './useInvoiceHistory'
import type { HistoryEntry } from './types'

const DIRECTION_LABEL: Record<string, string> = {
  recibida: 'Recibida',
  emitida: 'Emitida',
}

export function InvoiceHistory() {
  const { user, logout } = useSession()
  const history = useInvoiceHistory()
  const setexStyle = user?.role === 'user'

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

  if (!setexStyle) {
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

  return (
    <div className="mx-auto w-[90%] max-w-[600px] py-6">
      <div className="space-y-4 rounded-xl border-t-4 border-sx-brand bg-gradient-to-b from-[#fafafa] via-[#f5f5f5] to-[#f0f0f0] p-5 text-sx-ink1 shadow-[0_8px_30px_rgba(0,0,0,.15)]">
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <SetexBadge />
            <h1 className="text-[1.6em] font-bold text-sx-ink1">Facturas</h1>
          </div>
          <button
            type="button"
            onClick={() => void logout()}
            className="rounded-md bg-sx-bad px-3 py-1.5 text-sm font-semibold text-white"
          >
            Salir
          </button>
        </header>

        <Link to={ROUTES.capture} className="inline-block text-sm text-sx-brand underline">
          ← Volver a capturar
        </Link>

        <h2 className="text-[1.2em] font-semibold text-sx-ink1">
          📋 Historial de facturas ({entries.length})
        </h2>

        {entries.length === 0 ? (
          <p className="text-sx-ink3">Sin facturas en los últimos 7 días.</p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-sx-line">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="bg-[#f7fafc] text-xs uppercase tracking-wide text-sx-ink3">
                <tr>
                  <th className="p-2">Proveedor / Cliente</th>
                  <th className="p-2">Tipo ID</th>
                  <th className="p-2">NIF / CIF</th>
                  <th className="p-2">Fecha</th>
                  <th className="p-2 text-right">Total</th>
                  <th className="p-2">Compra/Venta</th>
                </tr>
              </thead>
              <tbody data-testid="history-list">
                {entries.map((entry, i) => (
                  <SetexHistoryRow key={entry.id} entry={entry} striped={i % 2 === 1} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

function SetexHistoryRow({ entry, striped }: { entry: HistoryEntry; striped: boolean }) {
  const kind = setexTaxIdKind(entry.counterparty_tax_id)
  // Filas de autónomos (NIF/NIE) con un tinte cálido propio, distinto de la alternancia normal
  // (§13: "salvo proveedores autónomos, que usan #fffaf5/#fff7ed").
  const isPerson = kind === 'nif' || kind === 'nie'
  const bg = isPerson ? (striped ? '#fff7ed' : '#fffaf5') : striped ? '#fafbfc' : '#ffffff'
  const arrow = entry.direction === 'emitida' ? '↑ Emitida' : '↓ Recibida'

  return (
    <tr data-testid="history-row" style={{ background: bg }} className="border-t border-sx-line">
      <td className="max-w-[180px] truncate p-2" title={entry.counterparty_name ?? undefined}>
        {entry.counterparty_name ?? '—'}
      </td>
      <td className="p-2">
        {kind ? (
          <span className="rounded-full bg-sx-brand/10 px-2 py-0.5 text-xs font-medium text-sx-brand">
            {TAX_ID_LABEL[kind]}
          </span>
        ) : (
          <span className="text-sx-faint1">—</span>
        )}
      </td>
      <td className="whitespace-nowrap p-2 font-mono">{entry.counterparty_tax_id ?? '—'}</td>
      <td className="whitespace-nowrap p-2">{formatDate(entry.issue_date)}</td>
      <td className="whitespace-nowrap p-2 text-right font-semibold">
        {formatCurrency(entry.total_amount)}
      </td>
      <td className="whitespace-nowrap p-2">
        {entry.direction === 'emitida' ? (
          <span className="text-purple-700">{arrow}</span>
        ) : (
          <span className="text-sx-ivaText">{arrow}</span>
        )}
      </td>
    </tr>
  )
}

function HistoryRow({ entry }: { entry: HistoryEntry }) {
  return (
    <li data-testid="history-row" className="flex items-center justify-between gap-3 py-3">
      <div className="min-w-0">
        <p className="truncate font-medium">{entry.counterparty_name ?? '—'}</p>
        <p className="text-sm text-slate-400">
          {entry.issue_date ?? '—'} · {DIRECTION_LABEL[entry.direction] ?? entry.direction}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p className="font-semibold">{entry.total_amount ?? '—'}</p>
        <p className="text-sm text-slate-400">{entry.counterparty_cif_status}</p>
      </div>
    </li>
  )
}

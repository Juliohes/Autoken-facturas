import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ROUTES } from '../../app/routes'
import { usePendingSupervision } from './usePendingSupervision'
import type { SupervisionItem } from './types'

const STATUS_LABEL: Record<string, string> = {
  pending_ocr: 'En cola',
  processing: 'Procesando OCR',
  ocr_done: 'Lista para revisar',
  needs_review: 'Pendiente de revisión',
  ocr_failed: 'OCR fallido',
  capture_unreadable: 'Foto ilegible',
}

export function PendingSupervisionPanel() {
  const [cursor, setCursor] = useState<string | null>(null)
  const [items, setItems] = useState<SupervisionItem[]>([])
  const supervision = usePendingSupervision(cursor)

  useEffect(() => {
    if (!supervision.data) return
    setItems((current) => {
      if (cursor === null) return supervision.data.items
      const byId = new Map(current.map((item) => [item.id, item]))
      for (const item of supervision.data.items) byId.set(item.id, item)
      return Array.from(byId.values())
    })
  }, [cursor, supervision.data])

  if (supervision.isLoading && items.length === 0) {
    return <p className="p-6 text-slate-400">Cargando pendientes del equipo...</p>
  }
  if (supervision.isError && items.length === 0) {
    return <p role="alert" className="p-6 text-red-400">No se pudo cargar la supervisión.</p>
  }

  const hasMore = supervision.data?.next_cursor !== null && supervision.data?.next_cursor !== undefined
  return (
    <section className="tn-panel-page mx-auto max-w-4xl space-y-5 p-6">
      <div>
        <h1 className="text-xl font-semibold">Pendientes del equipo</h1>
        <p className="mt-1 text-sm text-slate-400">Vista de supervisión. La revisión es solo de lectura.</p>
      </div>
      {items.length === 0 ? (
        <p className="text-slate-400">No hay pendientes ajenos.</p>
      ) : (
        <div className="overflow-x-auto rounded-md border border-slate-700">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-800 text-slate-300">
              <tr>
                <th className="px-3 py-2">Usuario</th>
                <th className="px-3 py-2">Empresa</th>
                <th className="px-3 py-2">Estado</th>
                <th className="px-3 py-2">Subida</th>
                <th className="px-3 py-2">Páginas</th>
                <th className="px-3 py-2"><span className="sr-only">Acción</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className="border-t border-slate-700">
                  <td className="px-3 py-3">{item.user_email}</td>
                  <td className="px-3 py-3">{item.company_name}</td>
                  <td className="px-3 py-3">{STATUS_LABEL[item.status] ?? item.status}</td>
                  <td className="px-3 py-3">{formatDate(item.created_at)}</td>
                  <td className="px-3 py-3">{item.page_count}</td>
                  <td className="px-3 py-3">
                    <Link
                      to={ROUTES.supervisionReview(item.id)}
                      className="text-emerald-400"
                    >
                      Ver solo lectura
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {hasMore && (
        <button
          type="button"
          disabled={supervision.isFetching}
          onClick={() => setCursor(supervision.data?.next_cursor ?? null)}
          className="rounded-md border border-slate-600 px-4 py-2 text-sm disabled:opacity-50"
        >
          {supervision.isFetching ? 'Cargando...' : 'Cargar más'}
        </button>
      )}
    </section>
  )
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('es-ES')
}

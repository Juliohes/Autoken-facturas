import { useState } from 'react'

import { useSession } from '../session/SessionProvider'
import { useGlobalPending, useGlobalPendingReview } from './useGlobalPending'

export function GlobalPendingPanel() {
  const { user } = useSession()
  const [selection, setSelection] = useState<{ tenantId: string; fileId: string } | null>(null)
  const [cursors, setCursors] = useState<(string | null)[]>([null])
  const pageIndex = cursors.length - 1
  const pending = useGlobalPending(cursors[pageIndex], user?.is_admin_tech ?? false)
  const review = useGlobalPendingReview(selection?.tenantId ?? null, selection?.fileId ?? null, Boolean(user?.is_admin_tech))

  if (!user?.is_admin_tech) {
    return <p className="p-6 text-red-400" role="alert">No tienes acceso a esta pantalla.</p>
  }

  return (
    <section className="mx-auto max-w-6xl space-y-5 p-6 text-slate-100">
      <header>
        <h1 className="text-xl font-semibold">Pendientes globales</h1>
        <p className="mt-1 text-sm text-slate-400">Solo se abre un documento cuando lo seleccionas.</p>
      </header>

      {pending.isLoading && <p className="text-slate-400">Cargando pendientes...</p>}
      {pending.isError && <p className="text-red-400" role="alert">No se pudieron cargar los pendientes.</p>}
      {pending.data && pending.data.items.length === 0 && <p className="text-slate-400">No hay documentos pendientes.</p>}
      {pending.data && pending.data.items.length > 0 && (
        <div className="overflow-x-auto rounded border border-slate-700">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-800 text-slate-300">
              <tr><th className="p-3">Tenant</th><th className="p-3">Empresa</th><th className="p-3">Usuario</th><th className="p-3">Estado</th><th className="p-3" /></tr>
            </thead>
            <tbody>
              {pending.data.items.map((item) => (
                <tr className="border-t border-slate-800" key={`${item.tenant_id}:${item.id}`}>
                  <td className="p-3">{item.tenant_slug}</td>
                  <td className="p-3">{item.company_name}</td>
                  <td className="p-3">{item.user_email}</td>
                  <td className="p-3">{item.status}</td>
                  <td className="p-3 text-right">
                    <button
                      className="rounded bg-slate-700 px-3 py-1.5 hover:bg-slate-600"
                      onClick={() => setSelection({ tenantId: item.tenant_id, fileId: item.id })}
                      type="button"
                    >
                      Abrir en solo lectura
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pending.data && (pageIndex > 0 || pending.data.next_cursor) && (
        <div className="flex gap-2">
          <button
            className="rounded border border-slate-700 px-3 py-1.5 text-sm disabled:opacity-40"
            disabled={pageIndex === 0}
            onClick={() => setCursors((current) => current.slice(0, -1))}
            type="button"
          >
            Anterior
          </button>
          <button
            className="rounded bg-slate-700 px-3 py-1.5 text-sm disabled:opacity-40"
            disabled={!pending.data.next_cursor}
            onClick={() => {
              if (pending.data?.next_cursor) {
                setCursors((current) => [...current, pending.data!.next_cursor])
              }
            }}
            type="button"
          >
            Siguiente
          </button>
        </div>
      )}

      {selection && (
        <article className="rounded border border-slate-700 bg-slate-800/50 p-4">
          <h2 className="font-medium">Documento seleccionado</h2>
          {review.isLoading && <p className="mt-3 text-slate-400">Abriendo y registrando la consulta...</p>}
          {review.isError && <p className="mt-3 text-red-400" role="alert">No se pudo abrir el documento.</p>}
          {review.data && <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap text-xs text-slate-300">{JSON.stringify(review.data, null, 2)}</pre>}
        </article>
      )}
    </section>
  )
}

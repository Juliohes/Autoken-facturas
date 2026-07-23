// Sección de registros pendientes de aprobación (S3.4): reutiliza `GET /registrations` y
// `approve`/`reject` de S1.4, sin pantalla propia hasta ahora. Componente propio para que
// `CompaniesPanel` no orqueste dos fuentes de datos con la misma responsabilidad de presentación.
import { usePendingRegistrations } from './usePendingRegistrations'
import { useRegistrationDecision } from './useRegistrationDecision'

export function PendingRegistrations() {
  const registrations = usePendingRegistrations()
  const decide = useRegistrationDecision()

  const rows = registrations.data ?? []

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Registros pendientes de aprobación</h2>

      {registrations.isLoading && <p className="text-slate-400">Cargando…</p>}

      {registrations.isError && (
        <p role="alert" className="text-red-400">
          No se pudieron cargar los registros pendientes.
        </p>
      )}

      {decide.isError && (
        <p role="alert" className="text-sm text-red-400">
          {decide.error instanceof Error ? decide.error.message : 'No se pudo procesar el registro.'}
        </p>
      )}

      {!registrations.isLoading && !registrations.isError && rows.length === 0 && (
        <p className="text-slate-400">No hay registros pendientes.</p>
      )}

      {rows.length > 0 && (
        <table className="w-full text-left text-sm" data-testid="registrations-table">
          <thead className="text-slate-400">
            <tr>
              <th className="p-2">Email</th>
              <th className="p-2">Empresa</th>
              <th className="p-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-700">
            {rows.map((r) => (
              <tr key={r.id} data-testid="registration-row">
                <td className="p-2">{r.email}</td>
                <td className="p-2">
                  {r.company ?? '—'}
                  {r.joins_existing_company && (
                    <span className="ml-1 text-xs text-amber-400">(se une a empresa existente)</span>
                  )}
                </td>
                <td className="p-2 space-x-2">
                  <button
                    type="button"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ userId: r.id, decision: 'approve' })}
                    className="text-emerald-400 underline disabled:opacity-40"
                  >
                    Aprobar
                  </button>
                  <button
                    type="button"
                    disabled={decide.isPending}
                    onClick={() => decide.mutate({ userId: r.id, decision: 'reject' })}
                    className="text-red-400 underline disabled:opacity-40"
                  >
                    Rechazar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

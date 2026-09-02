// Sección de registros pendientes de aprobación (S3.4): reutiliza `GET /registrations` y
// `approve`/`reject` de S1.4, sin pantalla propia hasta ahora. Componente propio para que
// `CompaniesPanel` no orqueste dos fuentes de datos con la misma responsabilidad de presentación.
//
// Columnas redimensionables/ordenables (2026-08-10, "todas las tablas de todas las URL"), mismo
// mecanismo que `CompaniesPanel`.
import { getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { useMemo } from 'react'

import { DataTableTh } from '../../shared/DataTableTh'
import { usePersistedTableState } from '../../shared/usePersistedTableState'
import { usePendingRegistrations } from './usePendingRegistrations'
import { useRegistrationDecision } from './useRegistrationDecision'
import type { PendingRegistration } from './types'

const HEADER_LABELS: Record<string, string> = {
  email: 'Email',
  company: 'Empresa',
}

export function PendingRegistrations() {
  const registrations = usePendingRegistrations()
  const decide = useRegistrationDecision()

  const rows = useMemo(() => registrations.data ?? [], [registrations.data])
  const { columnSizing, onColumnSizingChange, columnSizingInfo, onColumnSizingInfoChange, sorting, setSorting } =
    usePersistedTableState('pending-registrations-column-widths')
  const columns = useMemo<ColumnDef<PendingRegistration, unknown>[]>(
    () => [
      { id: 'email', header: 'Email', accessorFn: (r) => r.email, size: 220, minSize: 32 },
      { id: 'company', header: 'Empresa', accessorFn: (r) => r.company ?? undefined, size: 200, minSize: 32, sortUndefined: 'last' },
      { id: 'actions', header: '', size: 160, enableSorting: false, enableResizing: false },
    ],
    [],
  )
  const table = useReactTable({
    data: rows,
    columns,
    state: { columnSizing, columnSizingInfo, sorting },
    onColumnSizingChange,
    onColumnSizingInfoChange,
    onSortingChange: setSorting,
    columnResizeMode: 'onChange',
    sortDescFirst: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })
  const sortedRows = table.getRowModel().rows.map((r) => r.original)

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
        <div className="overflow-x-auto">
          <table
            className="whitespace-nowrap text-left text-sm"
            style={{ tableLayout: 'fixed', width: table.getTotalSize() }}
            data-testid="registrations-table"
          >
            <thead className="text-slate-400">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <DataTableTh key={header.id} header={header} label={HEADER_LABELS[header.id] ?? ''} />
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-slate-700">
              {sortedRows.map((r) => (
                <tr key={r.id} data-testid="registration-row">
                  <td className="truncate p-2">
                    <span>{r.email}</span>
                    {r.email_verified ? (
                      <span className="ml-1 text-xs text-emerald-400">(email verificado)</span>
                    ) : (
                      <span className="ml-1 text-xs text-slate-500">(email sin verificar)</span>
                    )}
                  </td>
                  <td className="truncate p-2">
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
        </div>
      )}
    </section>
  )
}

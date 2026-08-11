// Pantalla del benchmark real multi-variante x multi-motor (S6.7, Área C+D): sustituye a
// `OcrRanking` (S4.8) en la ruta /plataforma/ranking-ocr -- aquel sigue existiendo en el repo sin
// enlazar (spec S6.7 §6), este es su sucesor. A diferencia de S4.8 (un ranking agregado por motor
// sin variantes de preprocesado), aquí el backend compara cada combinación variante+motor por
// grupo de campo de oro (C18: no existe un "mejor motor" único razonable entre CIF/NIF, importes y
// fecha -- cada campo tiene su propia combinación ganadora) y expone además la tabla completa de
// combinaciones (C20) y el propio panel del lote retroactivo con candado real (C10-C17, spec
// §0.5 "panel completo con botón + progreso").
import { useQueryClient } from '@tanstack/react-query'
import { getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { useEffect, useMemo, useRef, useState } from 'react'

import { DataTableTh } from '../../shared/DataTableTh'
import { ScrollableTable } from '../../shared/ScrollableTable'
import { usePersistedTableState } from '../../shared/usePersistedTableState'
import { useSession } from '../session/SessionProvider'
import { useBenchmarkBackfillStatus } from './useBenchmarkBackfillStatus'
import { useBenchmarkRanking } from './useBenchmarkRanking'
import { useStartBenchmarkBackfill } from './useStartBenchmarkBackfill'

type BenchmarkRankingData = NonNullable<ReturnType<typeof useBenchmarkRanking>['data']>
type FieldGroupRow = BenchmarkRankingData['by_field_group'][number]
type CombinationRow = BenchmarkRankingData['by_combination'][number]

const DEFAULT_LIMIT = 10

const COMBINATION_HEADER_LABELS: Record<string, string> = {
  variant: 'Variante',
  engine: 'Motor',
  executions: 'Ejecuciones',
  errors: 'Errores',
  aciertos: 'Aciertos',
  avg_duration_ms: 'Duración media',
}

// C18: agrupa las filas planas del backend por campo de oro (CIF/NIF, Fecha, Total…), cada grupo
// ordenado de mejor a peor ratio de acierto -- nunca un único ganador global, cada campo tiene el
// suyo. Los `null` (grupo sin ningún dato comparable todavía) se quedan al final.
function groupByField(rows: FieldGroupRow[]): Map<string, FieldGroupRow[]> {
  const groups = new Map<string, FieldGroupRow[]>()
  for (const row of rows) {
    const existing = groups.get(row.field_group)
    if (existing) existing.push(row)
    else groups.set(row.field_group, [row])
  }
  for (const entries of groups.values()) {
    entries.sort((a, b) => (b.ratio ?? -1) - (a.ratio ?? -1))
  }
  return groups
}

export function BenchmarkRanking() {
  const { user } = useSession()
  const isAdminTech = user?.is_admin_tech ?? false
  const queryClient = useQueryClient()

  // Mismo criterio que `OcrRanking`/`PlatformSettings` (S4.8/S4.10, hallazgo de auditoría): evita
  // peticiones que el backend rechazaría de todos modos (403) cuando el usuario no tiene el flag.
  const ranking = useBenchmarkRanking(isAdminTech)
  const status = useBenchmarkBackfillStatus(isAdminTech)
  const startBackfill = useStartBenchmarkBackfill()

  const [limit, setLimit] = useState(DEFAULT_LIMIT)
  // C10/C11: en cuanto la mutación resuelve (arrancó de verdad, o 409 porque ya había un lote
  // corriendo), el panel pasa a "Procesando…" de inmediato -- no espera al primer sondeo, que en
  // el peor caso tarda hasta 4s y en los tests de esta pantalla el estado mockeado nunca cambia
  // por sí solo.
  const [pendingStart, setPendingStart] = useState(false)
  const previousRunningRef = useRef<boolean | undefined>(undefined)

  const isRunning = status.data?.running ?? false
  const batch = status.data?.batch ?? null

  // C13/C17: cuando el sondeo detecta que un lote que SÍ estaba corriendo ya terminó, vuelve al
  // botón inicial y refresca el ranking (los resultados nuevos ya están guardados en ese momento).
  useEffect(() => {
    if (previousRunningRef.current === true && isRunning === false) {
      setPendingStart(false)
      void queryClient.invalidateQueries({ queryKey: ['benchmark-ranking'] })
    }
    previousRunningRef.current = isRunning
  }, [isRunning, queryClient])

  const groups = useMemo(() => groupByField(ranking.data?.by_field_group ?? []), [ranking.data])
  const combinations = useMemo(() => ranking.data?.by_combination ?? [], [ranking.data])

  const {
    columnSizing,
    onColumnSizingChange,
    columnSizingInfo,
    onColumnSizingInfoChange,
    sorting,
    setSorting,
  } = usePersistedTableState('benchmark-ranking-column-widths')
  const columns = useMemo<ColumnDef<CombinationRow, unknown>[]>(
    () => [
      { id: 'variant', header: 'Variante', accessorFn: (r) => r.variant, size: 130, minSize: 32 },
      { id: 'engine', header: 'Motor', accessorFn: (r) => r.engine, size: 170, minSize: 32 },
      {
        id: 'executions',
        header: 'Ejecuciones',
        accessorFn: (r) => r.executions,
        size: 110,
        minSize: 32,
      },
      { id: 'errors', header: 'Errores', accessorFn: (r) => r.errors, size: 100, minSize: 32 },
      {
        id: 'aciertos',
        header: 'Aciertos',
        accessorFn: (r) => (r.comparables > 0 ? r.aciertos / r.comparables : 0),
        size: 120,
        minSize: 32,
      },
      {
        id: 'avg_duration_ms',
        header: 'Duración media',
        accessorFn: (r) => r.avg_duration_ms ?? -1,
        size: 140,
        minSize: 32,
      },
    ],
    [],
  )
  const table = useReactTable({
    data: combinations,
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
  const sortedCombinations = table.getRowModel().rows.map((r) => r.original)

  // C9 (mismo patrón que S4.8/S4.10): un platform_admin sin el flag nunca ve esta pantalla, aunque
  // entre a la URL a mano -- la ruta ya está protegida por rol (app/routes.ts); esta comprobación
  // es la del flag en sí.
  if (!isAdminTech) {
    return (
      <div className="p-6">
        <p className="text-red-400" role="alert">
          No tienes acceso a esta pantalla.
        </p>
      </div>
    )
  }

  const showProcessing = isRunning || pendingStart

  const handleStart = () => {
    startBackfill.mutate(limit, { onSuccess: () => setPendingStart(true) })
  }

  return (
    <section className="mx-auto max-w-5xl space-y-6 p-6 text-slate-100">
      <h1 className="text-xl font-semibold">Ranking OCR multi-modelo</h1>
      <p className="text-sm text-slate-400">
        Comparativa real de cada variante de preprocesado por motor candidato, ejecutada sobre las
        facturas ya confirmadas. Sin un único ganador global: cada campo (CIF/NIF, importes,
        fecha…) tiene su propia combinación más fiable.
      </p>

      <div className="space-y-2 rounded border border-slate-800 p-4">
        {status.isLoading && <p className="text-slate-400">Cargando estado del lote…</p>}

        {!status.isLoading && showProcessing && (
          <p className="text-slate-200">
            {isRunning && batch ? `Procesando… (${batch.completed}/${batch.total})` : 'Procesando…'}
          </p>
        )}

        {!status.isLoading && !showProcessing && (
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-400">
              Nº de facturas
              <input
                type="number"
                min={1}
                value={limit}
                onChange={(e) => setLimit(Math.max(1, Number(e.target.value) || 1))}
                className="w-20 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
              />
            </label>
            <button
              type="button"
              onClick={handleStart}
              disabled={startBackfill.isPending}
              className="rounded bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {startBackfill.isPending ? 'Iniciando…' : `▶ Últimas ${limit}`}
            </button>
          </div>
        )}

        {startBackfill.isError && (
          <p role="alert" className="text-sm text-red-400">
            No se pudo iniciar el lote. Inténtalo de nuevo.
          </p>
        )}
      </div>

      {ranking.isLoading && <p className="text-slate-400">Cargando ranking…</p>}

      {ranking.isError && (
        <p role="alert" className="text-red-400">
          No se pudo cargar el ranking. Inténtalo de nuevo.
        </p>
      )}

      {ranking.data && groups.size === 0 && combinations.length === 0 && (
        <p className="text-slate-400">
          Todavía no hay ninguna ejecución del benchmark (lanza un lote arriba, o espera a que
          termine el que ya esté en marcha).
        </p>
      )}

      {groups.size > 0 && (
        <div className="space-y-4">
          <h2 className="text-base font-semibold text-slate-100">Mejor combinación por campo</h2>
          {[...groups.entries()].map(([fieldGroup, entries]) => (
            <section key={fieldGroup} className="space-y-3 rounded border border-slate-800 p-4">
              <h2 className="text-sm font-semibold text-slate-200">{fieldGroup}</h2>
              <ul className="space-y-2">
                {entries.map((entry) => (
                  <li key={`${entry.variant}-${entry.engine}`} className="space-y-1">
                    <div className="flex items-center justify-between text-xs text-slate-400">
                      <span>
                        {entry.engine} ({entry.variant})
                      </span>
                      <span>
                        {entry.ratio == null ? 'sin datos' : `${Math.round(entry.ratio * 100)}%`}
                      </span>
                    </div>
                    {entry.ratio == null ? (
                      <p className="text-xs text-slate-500">Sin comparables todavía.</p>
                    ) : (
                      <div className="h-2 w-full rounded bg-slate-800">
                        <div
                          className="h-2 rounded bg-emerald-500"
                          style={{ width: `${Math.max(0, Math.min(100, entry.ratio * 100))}%` }}
                        />
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      {combinations.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-base font-semibold text-slate-100">Todas las combinaciones</h2>
          <ScrollableTable>
            <table
              className="whitespace-nowrap text-left text-sm"
              style={{ tableLayout: 'fixed', width: table.getTotalSize() }}
            >
              <thead>
                {table.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id} className="border-b border-slate-700 text-slate-400">
                    {headerGroup.headers.map((header) => (
                      <DataTableTh
                        key={header.id}
                        header={header}
                        label={COMBINATION_HEADER_LABELS[header.id] ?? ''}
                      />
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody>
                {sortedCombinations.map((row) => (
                  <tr key={`${row.variant}-${row.engine}`} className="border-b border-slate-800">
                    <td className="truncate py-2 pr-4">{row.variant}</td>
                    <td className="truncate py-2 pr-4 font-medium">{row.engine}</td>
                    <td className="truncate py-2 pr-4">{row.executions}</td>
                    <td className="truncate py-2 pr-4">{row.errors}</td>
                    <td className="truncate py-2 pr-4">
                      {row.aciertos}/{row.comparables}
                    </td>
                    <td className="truncate py-2 pr-4">
                      {row.avg_duration_ms == null ? 'N/D' : `${Math.round(row.avg_duration_ms)} ms`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollableTable>
        </div>
      )}
    </section>
  )
}

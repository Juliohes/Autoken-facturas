// Pantalla del ranking multi-modelo (S4.8): agregado por motor, ordenado por puntuación media
// (ya lo devuelve así el backend). Solo lectura, sin gráficas ni historial (spec §6).
// "Ver ejemplos" (2026-08-09, a petición de Julio: "más contexto, ver ejemplos concretos, no solo
// números") abre una ventana con hasta 5 lecturas reales de ese motor, no solo el agregado.
//
// Columnas redimensionables/ordenables (2026-08-10, a petición de Julio: "todas las tablas de
// todas las URL"), mismo mecanismo que `CompaniesPanel`/`InvoicesPanel` (TanStack Table solo para
// el ancho/orden de cabecera; el cuerpo lo sigue pintando esta pantalla tal cual).
import { getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { useMemo, useState } from 'react'

import { DataTableTh } from '../../shared/DataTableTh'
import { ScrollableTable } from '../../shared/ScrollableTable'
import { usePersistedTableState } from '../../shared/usePersistedTableState'
import { useSession } from '../session/SessionProvider'
import { ExamplesModal } from './ExamplesModal'
import { useOcrRanking } from './useOcrRanking'

type RankingRow = NonNullable<ReturnType<typeof useOcrRanking>['data']>[number]

const HEADER_LABELS: Record<string, string> = {
  engine: 'Motor',
  invoices_read: 'Facturas leídas',
  average_score: 'Puntuación media',
  first_place_count: 'Primer puesto',
}

// Asimetría de motores documentada en la spec (§0): Azure DocIntel y Mistral OCR4 NO son modelos de
// lenguaje "promptables" (no se les puede pedir un JSON de campos); Azure mapea su propio esquema de
// `prebuilt-invoice`, y Mistral es OCR puro (siempre devuelve campos vacíos, por diseño de su API, no
// un fallo del motor). La spec exige que el panel muestre esta distinción, no solo el código.
const ENGINES_SIN_CAMPOS_PROMPTABLES = new Set(['azure-docintel', 'mistral-ocr-4'])

export function OcrRanking() {
  const { user } = useSession()
  const [examplesEngine, setExamplesEngine] = useState<string | null>(null)
  // Mismo criterio que PlatformSettings (S4.10, hallazgo de auditoría): evita un GET que el
  // backend rechazaría de todos modos (403) cuando el usuario no tiene el flag.
  const ranking = useOcrRanking(user?.is_admin_tech ?? false)
  const rows = useMemo(() => ranking.data ?? [], [ranking.data])
  const { columnSizing, onColumnSizingChange, columnSizingInfo, onColumnSizingInfoChange, sorting, setSorting } =
    usePersistedTableState('ocr-ranking-column-widths')
  const columns = useMemo<ColumnDef<RankingRow, unknown>[]>(
    () => [
      { id: 'engine', header: 'Motor', accessorFn: (r) => r.engine, size: 200, minSize: 32 },
      {
        id: 'invoices_read',
        header: 'Facturas leídas',
        accessorFn: (r) => r.invoices_read,
        size: 130,
        minSize: 32,
      },
      {
        id: 'average_score',
        header: 'Puntuación media',
        accessorFn: (r) => r.average_score,
        size: 140,
        minSize: 32,
      },
      {
        id: 'first_place_count',
        header: 'Primer puesto',
        accessorFn: (r) => r.first_place_count,
        size: 120,
        minSize: 32,
      },
      { id: 'examples', header: 'Ejemplos', size: 110, enableSorting: false, enableResizing: false },
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

  // C10: un platform_admin sin el flag nunca ve el ranking, aunque entre a la URL a mano — la
  // ruta ya está protegida por rol (app/routes.ts); esta comprobación es la del flag en sí.
  if (!user?.is_admin_tech) {
    return (
      <div className="p-6">
        <p className="text-red-400" role="alert">
          No tienes acceso a esta pantalla.
        </p>
      </div>
    )
  }

  return (
    <section className="tn-panel-page mx-auto max-w-3xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Ranking OCR multi-modelo</h1>
      <p className="text-sm text-slate-400">
        Puntuación media de cada motor candidato sobre las facturas ya procesadas con el
        experimento activo, ordenado de mejor a peor.
      </p>

      {ranking.isLoading && <p className="text-slate-400">Cargando…</p>}

      {ranking.isError && (
        <p role="alert" className="text-red-400">
          No se pudo cargar el ranking. Inténtalo de nuevo.
        </p>
      )}

      {ranking.data && ranking.data.length === 0 && (
        <p className="text-slate-400">
          Todavía no hay facturas rankeadas (el experimento sigue apagado o no ha procesado nada
          aún).
        </p>
      )}

      {ranking.data && ranking.data.length > 0 && (
        <ScrollableTable>
          <table className="whitespace-nowrap text-left text-sm" style={{ tableLayout: 'fixed', width: table.getTotalSize() }}>
            <thead>
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id} className="border-b border-slate-700 text-slate-400">
                  {headerGroup.headers.map((header) => (
                    <DataTableTh key={header.id} header={header} label={HEADER_LABELS[header.id] ?? ''} />
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {sortedRows.map((row) => (
                <tr key={row.engine} className="border-b border-slate-800">
                  <td className="truncate py-2 pr-4 font-medium">
                    {row.engine}
                    {ENGINES_SIN_CAMPOS_PROMPTABLES.has(row.engine) && (
                      <span
                        className="ml-2 text-xs font-normal text-slate-500"
                        title="Este motor no es un modelo de lenguaje promptable: sus campos vienen de su propio esquema (Azure DocIntel) o siempre están vacíos por diseño de su API (Mistral OCR4), no por un fallo de lectura."
                      >
                        (sin campos estructurados por diseño de su API)
                      </span>
                    )}
                  </td>
                  <td className="truncate py-2 pr-4">{row.invoices_read}</td>
                  <td className="truncate py-2 pr-4">{row.average_score.toFixed(2)}</td>
                  <td className="truncate py-2 pr-4">{row.first_place_count}</td>
                  <td className="truncate py-2 pr-4">
                    <button
                      type="button"
                      onClick={() => setExamplesEngine(row.engine)}
                      className="text-emerald-400 underline"
                    >
                      Ver ejemplos
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollableTable>
      )}

      {examplesEngine && (
        <ExamplesModal engine={examplesEngine} onClose={() => setExamplesEngine(null)} />
      )}
    </section>
  )
}

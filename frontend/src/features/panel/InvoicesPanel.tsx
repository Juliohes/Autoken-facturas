// Panel de facturas de la asesoría (S3.1). Editable desde 2026-08-01 (decisión de Julio): un único
// botón "Editar" activa la edición de cualquier celda de cualquier fila (no uno por fila); cada
// celda se guarda sola al perder el foco (`PATCH /invoices/{id}`, S3.3, reutilizado tal cual).
// "Ver" muestra la foto original vía la API (no una URL firmada de MinIO — inalcanzable desde el
// navegador en el despliegue real, ver `useInvoiceImage`). Los tramos de IVA se editan en su
// propia ventana (`TaxLinesModal`, un conjunto se guarda entero, no campo a campo).
//
// Columnas redimensionables (ratón o dedo) y ordenables por cabecera, estilo Excel (2026-08-10, a
// petición de Julio, ninguna depende del botón "Editar" de arriba). El ordenado es en memoria
// sobre las filas ya cargadas (`panel.data.pages`, S3.1 pagina por cursor): al pulsar "Cargar más"
// las páginas nuevas se re-ordenan junto a las ya visibles, no se pierden. TanStack Table (mismo
// motivo que `CompaniesPanel`: solo gestiona ancho/orden vía `getHeaderGroups`, el cuerpo lo sigue
// pintando `InvoiceTableRow` tal cual) sustituye al mecanismo casero anterior porque el
// redimensionado casero solo escuchaba al ratón.
import { getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { useMemo, useState } from 'react'

import {
  formatCurrency,
  formatDateTime,
  fromAmountInputValue,
  toAmountInputValue,
} from '../../shared/format'
import { DataTableTh } from '../../shared/DataTableTh'
import { ScrollableTable } from '../../shared/ScrollableTable'
import { usePersistedTableState } from '../../shared/usePersistedTableState'
import { useCompanyOptions } from '../companies/useCompanyOptions'
import { InvoiceImageModal } from './InvoiceImageModal'
import { TaxLinesModal } from './TaxLinesModal'
import { useEditInvoice } from './useEditInvoice'
import { useExportInvoices } from './useExportInvoices'
import { useInvoiceImage } from './useInvoiceImage'
import { useInvoicesPanel } from './useInvoicesPanel'
import type { InvoiceEditIn, InvoiceRow, PanelFilters } from './types'

const CIF_STATUS_OPTIONS = [
  { value: '', label: 'Todos' },
  { value: 'valid', label: 'Válido' },
  { value: 'invalid', label: 'Inválido' },
  { value: 'not_found', label: 'No consta' },
  { value: 'unverified', label: 'Sin verificar' },
]

function cleanFilters(raw: PanelFilters): PanelFilters {
  return Object.fromEntries(
    Object.entries(raw).filter(([, value]) => value !== undefined && value !== ''),
  ) as PanelFilters
}

// Etiquetas legibles de cada columna ordenable/redimensionable (para el `aria-label` del asa de
// arrastre; "Tramos IVA"/"Ver" no son columnas de dato, van fuera de este mapa). Anchos por
// defecto (px) en la definición de columnas de más abajo, persistidos por navegador (mismo patrón
// que `CompaniesPanel`).
const HEADER_LABELS: Record<string, string> = {
  company_name: 'Empresa',
  company_cif: 'CIF empresa',
  counterparty_name: 'Proveedor',
  counterparty_tax_id: 'CIF',
  issue_date: 'Fecha',
  net_amount: 'Base',
  tax_amount: 'IVA',
  total_amount: 'Total',
  irpf_amount: 'IRPF',
  uploaded_at: 'Subida',
}

/** `net_amount`/`tax_amount`/`total_amount`/`irpf_amount` llegan como texto decimal ("100.00",
 * nunca con coma — la coma es solo de presentación en el input). `parseFloat` basta para comparar
 * numéricamente al ordenar; `null`/vacío quedan fuera de la comparación (el hook los manda al
 * final). */
function parseAmount(value: string | null): number | null {
  if (value === null) return null
  const n = Number.parseFloat(value)
  return Number.isNaN(n) ? null : n
}

interface Props {
  /** Filtro inicial (S4.9): permite llegar aquí desde "Ver facturas" de una empresa ya filtrado. */
  initialFilters?: PanelFilters
}

export function InvoicesPanel({ initialFilters }: Props = {}) {
  const [rawFilters, setRawFilters] = useState<PanelFilters>(initialFilters ?? {})
  const filters = cleanFilters(rawFilters)
  const panel = useInvoicesPanel(filters)
  const companies = useCompanyOptions()
  const invoiceImage = useInvoiceImage()
  const exportInvoices = useExportInvoices()
  const [editing, setEditing] = useState(false)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [taxLinesFor, setTaxLinesFor] = useState<InvoiceRow | null>(null)

  const set = (patch: Partial<PanelFilters>) =>
    setRawFilters((prev) => ({ ...prev, ...patch }))

  const handleView = (uploadedFileId: string) => {
    invoiceImage.mutate(uploadedFileId, { onSuccess: (url) => setImageUrl(url) })
  }

  const closeImage = () => {
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    setImageUrl(null)
    invoiceImage.reset()
  }

  const handleExport = () => exportInvoices.mutate(filters)

  const rows = useMemo(() => panel.data?.pages.flatMap((page) => page.items) ?? [], [panel.data])
  const {
    columnSizing,
    onColumnSizingChange,
    columnSizingInfo,
    onColumnSizingInfoChange,
    sorting,
    setSorting,
  } = usePersistedTableState('invoices-panel-column-widths')

  // `?? undefined` en los campos que pueden ser `null` (contraparte, fecha, importes): con
  // `sortUndefined: 'last'` TanStack los manda siempre al final al ordenar, en cualquier dirección.
  const columns = useMemo<ColumnDef<InvoiceRow, unknown>[]>(
    () => [
      { id: 'company_name', header: 'Empresa', accessorFn: (r) => r.company_name, size: 140, minSize: 32 },
      { id: 'company_cif', header: 'CIF empresa', accessorFn: (r) => r.company_cif, size: 100, minSize: 32 },
      {
        id: 'counterparty_name',
        header: 'Proveedor',
        accessorFn: (r) => r.counterparty_name ?? undefined,
        size: 160,
        minSize: 32,
        sortUndefined: 'last',
      },
      {
        id: 'counterparty_tax_id',
        header: 'CIF',
        accessorFn: (r) => r.counterparty_tax_id ?? undefined,
        size: 100,
        minSize: 32,
        sortUndefined: 'last',
      },
      {
        id: 'issue_date',
        header: 'Fecha',
        accessorFn: (r) => r.issue_date ?? undefined,
        size: 90,
        minSize: 32,
        sortUndefined: 'last',
      },
      {
        id: 'net_amount',
        header: 'Base',
        accessorFn: (r) => parseAmount(r.net_amount) ?? undefined,
        size: 90,
        minSize: 32,
        sortUndefined: 'last',
      },
      {
        id: 'tax_amount',
        header: 'IVA',
        accessorFn: (r) => parseAmount(r.tax_amount) ?? undefined,
        size: 90,
        minSize: 32,
        sortUndefined: 'last',
      },
      {
        id: 'total_amount',
        header: 'Total',
        accessorFn: (r) => parseAmount(r.total_amount) ?? undefined,
        size: 90,
        minSize: 32,
        sortUndefined: 'last',
      },
      {
        id: 'irpf_amount',
        header: 'IRPF',
        accessorFn: (r) => parseAmount(r.irpf_amount) ?? undefined,
        size: 90,
        minSize: 32,
        sortUndefined: 'last',
      },
      { id: 'tax_lines', header: 'Tramos IVA', size: 110, enableSorting: false, enableResizing: false },
      { id: 'uploaded_at', header: 'Subida', accessorFn: (r) => r.uploaded_at, size: 130, minSize: 32 },
      { id: 'view', header: 'Ver', size: 64, enableSorting: false, enableResizing: false },
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
    // Primer clic siempre ascendente, sin importar el tipo de dato (ver mismo comentario en
    // `CompaniesPanel`).
    sortDescFirst: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })
  const sortedRows = table.getRowModel().rows.map((r) => r.original)

  return (
    <section className="mx-auto max-w-5xl space-y-4 p-6 text-slate-100">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Panel de facturas</h1>
        {/* Un único botón activa la edición de TODAS las celdas de TODAS las filas a la vez
            (2026-08-01, decisión de Julio: "no quiero un botón por fila"). */}
        <button
          type="button"
          onClick={() => setEditing((e) => !e)}
          className="rounded-md border border-slate-600 px-4 py-2 text-slate-100"
        >
          {editing ? 'Terminar edición' : 'Editar'}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <label className="flex flex-col text-sm text-slate-300">
          Desde
          <input
            type="date"
            value={rawFilters.date_from ?? ''}
            onChange={(e) => set({ date_from: e.target.value })}
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </label>
        <label className="flex flex-col text-sm text-slate-300">
          Hasta
          <input
            type="date"
            value={rawFilters.date_to ?? ''}
            onChange={(e) => set({ date_to: e.target.value })}
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </label>
        <label className="flex flex-col text-sm text-slate-300">
          CIF de contraparte
          <input
            type="text"
            value={rawFilters.counterparty_tax_id ?? ''}
            onChange={(e) => set({ counterparty_tax_id: e.target.value })}
            placeholder="CIF exacto"
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </label>
        <label className="flex flex-col text-sm text-slate-300">
          Estado del CIF
          <select
            value={rawFilters.cif_status ?? ''}
            onChange={(e) => set({ cif_status: e.target.value })}
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
          >
            {CIF_STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-sm text-slate-300">
          Empresa
          <select
            value={rawFilters.company_id ?? ''}
            onChange={(e) => set({ company_id: e.target.value })}
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
          >
            <option value="">Todas</option>
            {(companies.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <button
        type="button"
        onClick={handleExport}
        disabled={exportInvoices.isPending}
        className="rounded-md border border-slate-600 px-4 py-2 text-slate-100 disabled:opacity-40"
      >
        {exportInvoices.isPending ? 'Generando…' : 'Descargar Excel'}
      </button>
      {exportInvoices.isError && (
        <p role="alert" className="text-sm text-red-400">
          No se pudo generar el Excel. Inténtalo de nuevo.
        </p>
      )}

      {panel.isLoading && <p className="text-slate-400">Cargando…</p>}

      {panel.isError && (
        <p role="alert" className="text-red-400">
          No se pudo cargar el panel. Inténtalo de nuevo.
        </p>
      )}

      {!panel.isLoading && !panel.isError && rows.length === 0 && (
        <p className="text-slate-400">No hay facturas con estos filtros.</p>
      )}

      {!panel.isLoading && !panel.isError && rows.length > 0 && (
        <>
          {invoiceImage.isError && (
            <p role="alert" className="text-sm text-red-400">
              No se pudo cargar la imagen de la factura. Inténtalo de nuevo.
            </p>
          )}
          <ScrollableTable>
            <table
              className="whitespace-nowrap text-left text-sm"
              style={{ tableLayout: 'fixed', width: table.getTotalSize() }}
              data-testid="invoices-table"
            >
              <thead className="text-slate-400">
                {table.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <DataTableTh
                        key={header.id}
                        header={header}
                        label={HEADER_LABELS[header.id] ?? ''}
                      />
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody className="divide-y divide-slate-700">
                {sortedRows.map((row) => (
                  <InvoiceTableRow
                    key={row.id}
                    row={row}
                    editing={editing}
                    onView={handleView}
                    onOpenTaxLines={() => setTaxLinesFor(row)}
                  />
                ))}
              </tbody>
            </table>
          </ScrollableTable>

          {panel.hasNextPage && (
            <button
              type="button"
              onClick={() => panel.fetchNextPage()}
              disabled={panel.isFetchingNextPage}
              className="rounded-md border border-slate-600 px-4 py-2 text-slate-100 disabled:opacity-40"
            >
              {panel.isFetchingNextPage ? 'Cargando…' : 'Cargar más'}
            </button>
          )}
        </>
      )}

      {imageUrl && <InvoiceImageModal src={imageUrl} onClose={closeImage} />}
      {taxLinesFor && (
        <TaxLinesModal invoice={taxLinesFor} onClose={() => setTaxLinesFor(null)} />
      )}
    </section>
  )
}

type InvoiceField =
  | 'counterparty_name'
  | 'counterparty_tax_id'
  | 'issue_date'
  | 'net_amount'
  | 'tax_amount'
  | 'total_amount'
  | 'irpf_amount'

function patchFor(field: InvoiceField, value: string | null): InvoiceEditIn {
  switch (field) {
    case 'counterparty_name':
      return { counterparty_name: value }
    case 'counterparty_tax_id':
      return { counterparty_tax_id: value }
    case 'issue_date':
      return { issue_date: value }
    case 'net_amount':
      return { net_amount: value }
    case 'tax_amount':
      return { tax_amount: value }
    case 'total_amount':
      return { total_amount: value }
    case 'irpf_amount':
      return { irpf_amount: value }
  }
}

interface EditableCellProps {
  invoiceId: string
  field: InvoiceField
  value: string | null
  label: string
  type?: string
  /** Campo de importe (base/IVA/total/IRPF): se muestra y edita con coma decimal, nunca con punto
   * (2026-08-08, hallazgo de Julio: esta celda seguía mostrando el punto crudo del backend). */
  isAmount?: boolean
}

/** Una celda editable individual: se guarda sola al perder el foco, si el valor cambió de verdad
 * (2026-08-01, "cualquier celda editable" — sin un botón Guardar/Cancelar por fila). */
function EditableInvoiceCell({
  invoiceId,
  field,
  value,
  label,
  type = 'text',
  isAmount = false,
}: EditableCellProps) {
  const editInvoice = useEditInvoice()
  const current = isAmount ? toAmountInputValue(value) : (value ?? '')
  return (
    <div>
      <input
        // La `key` cambia si el valor real de la fila cambia (tras guardar o desde otra pestaña):
        // fuerza a React a remontar el input con el valor nuevo, sin sincronización manual.
        key={`${invoiceId}-${field}-${current}`}
        type={type}
        defaultValue={current}
        aria-label={label}
        disabled={editInvoice.isPending}
        onBlur={(e) => {
          const next = e.target.value
          if (next === current) return
          const body = isAmount ? fromAmountInputValue(next) : next === '' ? null : next
          editInvoice.mutate({ invoiceId, body: patchFor(field, body) })
        }}
        className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1 disabled:opacity-40"
      />
      {editInvoice.isError && (
        <p role="alert" className="text-xs text-red-400">
          {editInvoice.error instanceof Error ? editInvoice.error.message : 'No se pudo guardar.'}
        </p>
      )}
    </div>
  )
}

interface RowProps {
  row: InvoiceRow
  editing: boolean
  onView: (uploadedFileId: string) => void
  onOpenTaxLines: () => void
}

function InvoiceTableRow({ row, editing, onView, onOpenTaxLines }: RowProps) {
  const taxLinesLabel =
    row.tax_lines.length === 0
      ? 'Sin tramos'
      : `${row.tax_lines.length} tramo${row.tax_lines.length === 1 ? '' : 's'}`

  return (
    <tr data-testid="invoice-row">
      {/* Empresa CLIENTE del tenant (quién sube la factura): fija, nunca editable aquí — no es un
          dato del documento, es a quién pertenece (2026-08-01, hallazgo de Julio: el panel solo
          mostraba el proveedor/contraparte, nunca la propia empresa). */}
      <td className="truncate p-2">{row.company_name}</td>
      <td className="truncate p-2">{row.company_cif}</td>
      <td className="truncate p-2">
        {editing ? (
          <EditableInvoiceCell
            invoiceId={row.id}
            field="counterparty_name"
            value={row.counterparty_name}
            label="Proveedor"
          />
        ) : (
          (row.counterparty_name ?? '—')
        )}
      </td>
      <td className="truncate p-2">
        {editing ? (
          <EditableInvoiceCell
            invoiceId={row.id}
            field="counterparty_tax_id"
            value={row.counterparty_tax_id}
            label="CIF"
          />
        ) : (
          (row.counterparty_tax_id ?? '—')
        )}
      </td>
      <td className="truncate p-2">
        {editing ? (
          <EditableInvoiceCell
            invoiceId={row.id}
            field="issue_date"
            value={row.issue_date}
            label="Fecha"
            type="date"
          />
        ) : (
          (row.issue_date ?? '—')
        )}
      </td>
      <td className="truncate p-2">
        {editing ? (
          <EditableInvoiceCell
            invoiceId={row.id}
            field="net_amount"
            value={row.net_amount}
            label="Base"
            isAmount
          />
        ) : (
          formatCurrency(row.net_amount)
        )}
      </td>
      <td className="truncate p-2">
        {editing ? (
          <EditableInvoiceCell
            invoiceId={row.id}
            field="tax_amount"
            value={row.tax_amount}
            label="IVA"
            isAmount
          />
        ) : (
          formatCurrency(row.tax_amount)
        )}
      </td>
      <td className="truncate p-2">
        {editing ? (
          <EditableInvoiceCell
            invoiceId={row.id}
            field="total_amount"
            value={row.total_amount}
            label="Total"
            isAmount
          />
        ) : (
          formatCurrency(row.total_amount)
        )}
      </td>
      <td className="truncate p-2">
        {editing ? (
          <EditableInvoiceCell
            invoiceId={row.id}
            field="irpf_amount"
            value={row.irpf_amount}
            label="IRPF"
            isAmount
          />
        ) : (
          formatCurrency(row.irpf_amount)
        )}
      </td>
      <td className="truncate p-2">
        <button type="button" onClick={onOpenTaxLines} className="text-emerald-400 underline">
          {taxLinesLabel}
        </button>
      </td>
      <td className="truncate p-2">{formatDateTime(row.uploaded_at)}</td>
      <td className="truncate p-2">
        <button
          type="button"
          onClick={() => onView(row.uploaded_file_id)}
          className="text-emerald-400 underline"
        >
          Ver
        </button>
      </td>
    </tr>
  )
}

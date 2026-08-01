// Panel de facturas de la asesoría (S3.1): listado filtrado y paginado, solo
// lectura, para el `tenant_admin`. Orquesta los hooks de datos y la presentación;
// "Ver" reutiliza tal cual la URL firmada de S2.7, sin duplicar esa lógica.
// Comportamientos C13-C16 de la spec.
import { useState } from 'react'

import { formatCurrency, formatDateTime } from '../../shared/format'
import { ScrollableTable } from '../../shared/ScrollableTable'
import { useCompanyOptions } from '../companies/useCompanyOptions'
import { InvoiceHistoryPanel } from './InvoiceHistoryPanel'
import { useDownloadUrl } from './useDownloadUrl'
import { useEditInvoice } from './useEditInvoice'
import { useExportInvoices } from './useExportInvoices'
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

interface Props {
  /** Filtro inicial (S4.9): permite llegar aquí desde "Ver facturas" de una empresa ya filtrado. */
  initialFilters?: PanelFilters
}

export function InvoicesPanel({ initialFilters }: Props = {}) {
  const [rawFilters, setRawFilters] = useState<PanelFilters>(initialFilters ?? {})
  const filters = cleanFilters(rawFilters)
  const panel = useInvoicesPanel(filters)
  const companies = useCompanyOptions()
  const downloadUrl = useDownloadUrl()
  const exportInvoices = useExportInvoices()

  const set = (patch: Partial<PanelFilters>) =>
    setRawFilters((prev) => ({ ...prev, ...patch }))

  const handleView = (uploadedFileId: string) => {
    downloadUrl.mutate(uploadedFileId, {
      onSuccess: (url) => window.open(url, '_blank', 'noopener,noreferrer'),
    })
  }

  const handleExport = () => exportInvoices.mutate(filters)

  const rows = panel.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <section className="mx-auto max-w-5xl space-y-4 p-6 text-slate-100">
      <h1 className="text-xl font-semibold">Panel de facturas</h1>

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
          {downloadUrl.isError && (
            <p role="alert" className="text-sm text-red-400">
              No se pudo generar el enlace de la imagen. Inténtalo de nuevo.
            </p>
          )}
          <ScrollableTable>
            <table
              className="w-full whitespace-nowrap text-left text-sm"
              data-testid="invoices-table"
            >
              <thead className="text-slate-400">
                <tr>
                  <th className="p-2">Proveedor</th>
                  <th className="p-2">CIF</th>
                  <th className="p-2">Fecha</th>
                  <th className="p-2">Base</th>
                  <th className="p-2">IVA</th>
                  <th className="p-2">Total</th>
                  <th className="p-2">IRPF</th>
                  <th className="p-2">Tramos IVA</th>
                  <th className="p-2">Subida</th>
                  <th className="p-2">Acciones</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {rows.map((row) => (
                  <InvoiceTableRow key={row.id} row={row} onView={handleView} />
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
    </section>
  )
}

interface RowProps {
  row: InvoiceRow
  onView: (uploadedFileId: string) => void
}

const EDIT_COLUMN_COUNT = 10

function draftFrom(row: InvoiceRow) {
  return {
    counterparty_name: row.counterparty_name ?? '',
    counterparty_tax_id: row.counterparty_tax_id ?? '',
    issue_date: row.issue_date ?? '',
    net_amount: row.net_amount ?? '',
    tax_amount: row.tax_amount ?? '',
    total_amount: row.total_amount ?? '',
    irpf_amount: row.irpf_amount ?? '',
  }
}

function InvoiceTableRow({ row, onView }: RowProps) {
  const [editing, setEditing] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [draft, setDraft] = useState(draftFrom(row))
  const editInvoice = useEditInvoice()

  const startEditing = () => {
    setDraft(draftFrom(row))
    setEditing(true)
  }

  const save = () => {
    const body: InvoiceEditIn = {
      counterparty_name: draft.counterparty_name === '' ? null : draft.counterparty_name,
      counterparty_tax_id: draft.counterparty_tax_id === '' ? null : draft.counterparty_tax_id,
      issue_date: draft.issue_date === '' ? null : draft.issue_date,
      net_amount: draft.net_amount === '' ? null : draft.net_amount,
      tax_amount: draft.tax_amount === '' ? null : draft.tax_amount,
      total_amount: draft.total_amount === '' ? null : draft.total_amount,
      irpf_amount: draft.irpf_amount === '' ? null : draft.irpf_amount,
    }
    editInvoice.mutate({ invoiceId: row.id, body }, { onSuccess: () => setEditing(false) })
  }

  // El "Revertir a este valor" del historial es una edición más, independiente de si esta fila
  // está en modo edición ahora mismo (no toca `editing`).
  const revert = (body: InvoiceEditIn) => editInvoice.mutate({ invoiceId: row.id, body })

  const taxLinesText =
    row.tax_lines.length === 0
      ? '—'
      : row.tax_lines
          .map(
            (line) =>
              `${line.iva_pct ?? '—'}% (${formatCurrency(line.base)} → ${formatCurrency(line.cuota)})`,
          )
          .join(', ')

  if (editing) {
    return (
      <tr data-testid="invoice-row" data-editing="true">
        <td className="p-2">
          <input
            aria-label="Proveedor"
            value={draft.counterparty_name}
            onChange={(e) => setDraft((d) => ({ ...d, counterparty_name: e.target.value }))}
            className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </td>
        <td className="p-2">
          <input
            aria-label="CIF"
            value={draft.counterparty_tax_id}
            onChange={(e) => setDraft((d) => ({ ...d, counterparty_tax_id: e.target.value }))}
            className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </td>
        <td className="p-2">
          <input
            type="date"
            aria-label="Fecha"
            value={draft.issue_date}
            onChange={(e) => setDraft((d) => ({ ...d, issue_date: e.target.value }))}
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </td>
        <td className="p-2">
          <input
            aria-label="Base"
            value={draft.net_amount}
            onChange={(e) => setDraft((d) => ({ ...d, net_amount: e.target.value }))}
            className="w-20 rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </td>
        <td className="p-2">
          <input
            aria-label="IVA"
            value={draft.tax_amount}
            onChange={(e) => setDraft((d) => ({ ...d, tax_amount: e.target.value }))}
            className="w-20 rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </td>
        <td className="p-2">
          <input
            aria-label="Total"
            value={draft.total_amount}
            onChange={(e) => setDraft((d) => ({ ...d, total_amount: e.target.value }))}
            className="w-20 rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </td>
        <td className="p-2">
          <input
            aria-label="IRPF"
            value={draft.irpf_amount}
            onChange={(e) => setDraft((d) => ({ ...d, irpf_amount: e.target.value }))}
            className="w-20 rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </td>
        {/* Tramos de IVA: fuera de alcance de la edición inline (una lista de tramos, no un
            valor suelto); se sigue mostrando, solo de lectura. */}
        <td className="p-2" data-testid="tax-lines">
          {taxLinesText}
        </td>
        <td className="p-2">{formatDateTime(row.uploaded_at)}</td>
        <td className="p-2">
          <div className="flex flex-col gap-1">
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={save}
                disabled={editInvoice.isPending}
                className="text-emerald-400 underline disabled:opacity-40"
              >
                Guardar
              </button>
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="text-slate-400 underline"
              >
                Cancelar
              </button>
            </div>
            {editInvoice.isError && (
              <p role="alert" className="text-xs text-red-400">
                {editInvoice.error instanceof Error
                  ? editInvoice.error.message
                  : 'No se pudo guardar la factura.'}
              </p>
            )}
          </div>
        </td>
      </tr>
    )
  }

  return (
    <>
      <tr data-testid="invoice-row">
        <td className="p-2">{row.counterparty_name ?? '—'}</td>
        <td className="p-2">{row.counterparty_tax_id ?? '—'}</td>
        <td className="p-2">{row.issue_date ?? '—'}</td>
        <td className="p-2">{formatCurrency(row.net_amount)}</td>
        <td className="p-2">{formatCurrency(row.tax_amount)}</td>
        <td className="p-2">{formatCurrency(row.total_amount)}</td>
        <td className="p-2">{formatCurrency(row.irpf_amount)}</td>
        <td className="p-2" data-testid="tax-lines">
          {taxLinesText}
        </td>
        <td className="p-2">{formatDateTime(row.uploaded_at)}</td>
        <td className="p-2">
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={startEditing} className="text-emerald-400 underline">
              Editar
            </button>
            <button
              type="button"
              onClick={() => setHistoryOpen((open) => !open)}
              className="text-emerald-400 underline"
            >
              {historyOpen ? 'Ocultar historial' : 'Historial'}
            </button>
            <button
              type="button"
              onClick={() => onView(row.uploaded_file_id)}
              className="text-emerald-400 underline"
            >
              Ver
            </button>
          </div>
        </td>
      </tr>
      {historyOpen && (
        <tr data-testid="invoice-history-panel">
          <td colSpan={EDIT_COLUMN_COUNT} className="bg-slate-800/50 p-0">
            <InvoiceHistoryPanel invoiceId={row.id} onRevert={revert} saving={editInvoice.isPending} />
          </td>
        </tr>
      )}
    </>
  )
}

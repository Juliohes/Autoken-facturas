// Panel de facturas de la asesoría (S3.1): listado filtrado y paginado, solo
// lectura, para el `tenant_admin`. Orquesta los hooks de datos y la presentación;
// "Ver" reutiliza tal cual la URL firmada de S2.7, sin duplicar esa lógica.
// Comportamientos C13-C16 de la spec.
import { useState } from 'react'

import { useCompanyOptions } from '../companies/useCompanyOptions'
import { useDownloadUrl } from './useDownloadUrl'
import { useExportInvoices } from './useExportInvoices'
import { useInvoicesPanel } from './useInvoicesPanel'
import type { InvoiceRow, PanelFilters } from './types'

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
          Proveedor / CIF
          <input
            type="text"
            value={rawFilters.q ?? ''}
            onChange={(e) => set({ q: e.target.value })}
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
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="invoices-table">
              <thead className="text-slate-400">
                <tr>
                  <th className="p-2">Proveedor</th>
                  <th className="p-2">CIF</th>
                  <th className="p-2">Estado CIF</th>
                  <th className="p-2">Fecha</th>
                  <th className="p-2">Base</th>
                  <th className="p-2">IVA</th>
                  <th className="p-2">Total</th>
                  <th className="p-2">IRPF</th>
                  <th className="p-2">Tramos IVA</th>
                  <th className="p-2">Subida</th>
                  <th className="p-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {rows.map((row) => (
                  <InvoiceTableRow key={row.id} row={row} onView={handleView} />
                ))}
              </tbody>
            </table>
          </div>

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

function InvoiceTableRow({ row, onView }: RowProps) {
  return (
    <tr data-testid="invoice-row">
      <td className="p-2">{row.counterparty_name ?? '—'}</td>
      <td className="p-2">{row.counterparty_tax_id ?? '—'}</td>
      <td className="p-2">{row.counterparty_cif_status}</td>
      <td className="p-2">{row.issue_date ?? '—'}</td>
      <td className="p-2">{row.net_amount ?? '—'}</td>
      <td className="p-2">{row.tax_amount ?? '—'}</td>
      <td className="p-2">{row.total_amount ?? '—'}</td>
      <td className="p-2">{row.irpf_amount ?? '—'}</td>
      <td className="p-2" data-testid="tax-lines">
        {row.tax_lines.length === 0
          ? '—'
          : row.tax_lines
              .map((line) => `${line.iva_pct ?? '—'}% (${line.base ?? '—'} → ${line.cuota ?? '—'})`)
              .join(', ')}
      </td>
      <td className="p-2">{row.uploaded_at}</td>
      <td className="p-2">
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

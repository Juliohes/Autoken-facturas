// Laboratorio OCR (S6.2): diagnóstico por factura, solo panel de plataforma (admin-tech). Elige un
// tenant -> lista sus facturas confirmadas (solo lectura) -> "Ver" (la foto) / "Laboratorio" (las 3
// lecturas + comparativa de modelos). El panel de facturas de cada tenant no cambia en nada (C3):
// esta pantalla no importa nada de `features/panel`, salvo `InvoiceImageModal` (presentación pura,
// sin acoplarse a datos tenant-scoped).
//
// Las 3 tablas (facturas del tenant, correcciones de la Lectura 3, comparativa de modelos) son
// redimensionables/ordenables (2026-08-10, "todas las tablas de todas las URL"), mismo mecanismo
// que `CompaniesPanel`/`InvoicesPanel`.
import { getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { useMemo, useState } from 'react'

import { DataTableTh } from '../../shared/DataTableTh'
import { formatCurrency, formatDateTime } from '../../shared/format'
import { usePersistedTableState } from '../../shared/usePersistedTableState'
import { InvoiceImageModal } from '../panel/InvoiceImageModal'
import { useSession } from '../session/SessionProvider'
import type { LabDetail, LabInvoiceRow, RankingEntry, Reading3Correction } from './labTypes'
import { useInvoiceLab } from './useInvoiceLab'
import { useTenantInvoiceImage } from './useTenantInvoiceImage'
import { useTenantInvoices } from './useTenantInvoices'
import { useTenants } from './useTenants'

const INVOICE_HEADER_LABELS: Record<string, string> = {
  company_name: 'Empresa',
  counterparty_name: 'Proveedor',
  issue_date: 'Fecha',
  total_amount: 'Total',
  confirmed_at: 'Confirmada',
}

export function PlatformLab() {
  const { user } = useSession()
  const [tenantId, setTenantId] = useState<string | null>(null)
  const [labFileId, setLabFileId] = useState<string | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)

  const isAdminTech = user?.is_admin_tech ?? false
  const tenants = useTenants(isAdminTech)
  const invoices = useTenantInvoices(isAdminTech ? tenantId : null)
  const lab = useInvoiceLab(isAdminTech ? tenantId : null, labFileId)
  const image = useTenantInvoiceImage()

  // Reglas de hooks de React: todos los hooks (incluidos los de la tabla) deben llamarse ANTES de
  // cualquier `return` condicional (C1 más abajo), sin importar que la tabla no llegue a pintarse
  // cuando falta el flag `is_admin_tech`.
  const rows = useMemo(() => invoices.data ?? [], [invoices.data])
  const { columnSizing, onColumnSizingChange, columnSizingInfo, onColumnSizingInfoChange, sorting, setSorting } =
    usePersistedTableState('platform-lab-invoices-column-widths')
  const columns = useMemo<ColumnDef<LabInvoiceRow, unknown>[]>(
    () => [
      { id: 'company_name', header: 'Empresa', accessorFn: (r) => r.company_name, size: 160, minSize: 32 },
      {
        id: 'counterparty_name',
        header: 'Proveedor',
        accessorFn: (r) => r.counterparty_name ?? undefined,
        size: 160,
        minSize: 32,
        sortUndefined: 'last',
      },
      {
        id: 'issue_date',
        header: 'Fecha',
        accessorFn: (r) => r.issue_date ?? undefined,
        size: 100,
        minSize: 32,
        sortUndefined: 'last',
      },
      {
        id: 'total_amount',
        header: 'Total',
        accessorFn: (r) => (r.total_amount === null ? undefined : Number.parseFloat(r.total_amount)),
        size: 100,
        minSize: 32,
        sortUndefined: 'last',
      },
      { id: 'confirmed_at', header: 'Confirmada', accessorFn: (r) => r.confirmed_at, size: 140, minSize: 32 },
      { id: 'view', header: 'Ver', size: 64, enableSorting: false, enableResizing: false },
      { id: 'lab', header: 'Laboratorio', size: 110, enableSorting: false, enableResizing: false },
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

  // C1: un platform_admin sin el flag nunca ve el selector ni dispara ningún GET (evita un 403
  // predecible), aunque entre a la URL a mano — la ruta ya está protegida por rol (app/routes.ts).
  if (!isAdminTech) {
    return (
      <div className="p-6">
        <p className="text-red-400" role="alert">
          No tienes acceso a esta pantalla.
        </p>
      </div>
    )
  }

  const handleView = (fileId: string) => {
    if (!tenantId) return
    image.mutate({ tenantId, fileId }, { onSuccess: (url) => setImageUrl(url) })
  }

  const closeImage = () => {
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    setImageUrl(null)
    image.reset()
  }

  return (
    <section className="mx-auto max-w-5xl space-y-4 p-6 text-slate-100">
      <h1 className="text-xl font-semibold">Laboratorio OCR</h1>
      <p className="text-sm text-slate-400">
        Diagnóstico por factura: Lectura 1 (lo que leyó la IA), Lectura 2 (tras los ajustes
        internos), Lectura 3 (lo guardado tras tus cambios) y la comparativa de modelos. Solo
        lectura, herramienta interna temporal.
      </p>

      <label className="flex max-w-xs flex-col gap-1 text-sm text-slate-300">
        Tenant
        <select
          aria-label="Tenant"
          value={tenantId ?? ''}
          onChange={(e) => {
            setTenantId(e.target.value || null)
            setLabFileId(null)
          }}
          className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
        >
          <option value="">Elige un tenant…</option>
          {(tenants.data ?? []).map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>

      {tenantId && invoices.isLoading && <p className="text-slate-400">Cargando facturas…</p>}
      {tenantId && invoices.isError && (
        <p role="alert" className="text-red-400">
          No se pudieron cargar las facturas de este tenant.
        </p>
      )}
      {tenantId && !invoices.isLoading && !invoices.isError && rows.length === 0 && (
        <p className="text-slate-400">Este tenant no tiene facturas confirmadas todavía.</p>
      )}

      {tenantId && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="whitespace-nowrap text-left text-sm" style={{ tableLayout: 'fixed', width: table.getTotalSize() }}>
            <thead className="text-slate-400">
              {table.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <DataTableTh
                      key={header.id}
                      header={header}
                      label={INVOICE_HEADER_LABELS[header.id] ?? ''}
                    />
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-slate-800">
              {sortedRows.map((row) => (
                <tr key={row.id} data-testid="lab-invoice-row">
                  <td className="truncate p-2">{row.company_name}</td>
                  <td className="truncate p-2">{row.counterparty_name ?? '—'}</td>
                  <td className="truncate p-2">{row.issue_date ?? '—'}</td>
                  <td className="truncate p-2">{formatCurrency(row.total_amount)}</td>
                  <td className="truncate p-2">{formatDateTime(row.confirmed_at)}</td>
                  <td className="truncate p-2">
                    <button
                      type="button"
                      onClick={() => handleView(row.uploaded_file_id)}
                      className="text-emerald-400 underline"
                    >
                      Ver
                    </button>
                  </td>
                  <td className="truncate p-2">
                    <button
                      type="button"
                      onClick={() => setLabFileId(row.uploaded_file_id)}
                      className="text-emerald-400 underline"
                    >
                      Laboratorio
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {labFileId && lab.isLoading && <p className="text-slate-400">Cargando laboratorio…</p>}
      {labFileId && lab.isError && (
        <p role="alert" className="text-red-400">
          No se pudo cargar el laboratorio de esta factura.
        </p>
      )}
      {labFileId && lab.data && (
        <LabDetailModal detail={lab.data} onClose={() => setLabFileId(null)} />
      )}

      {imageUrl && <InvoiceImageModal src={imageUrl} onClose={closeImage} />}
      {image.isError && (
        <p role="alert" className="text-sm text-red-400">
          No se pudo cargar la imagen de la factura.
        </p>
      )}
    </section>
  )
}

function scalarFields(fields: Record<string, unknown>): [string, unknown][] {
  return Object.entries(fields).filter(
    ([, value]) => value === null || typeof value !== 'object',
  )
}

/** Tramos de IVA de la Lectura 2 (`ReviewTaxLine[]`, claves `rate`/`base`/`cuota`) o de la Lectura 3
 * (`_invoice_dict`, claves `iva_pct`/`base`/`cuota`): `scalarFields` los descarta por ser un array,
 * así que se muestran aparte (hallazgo de auditoría: quedaban invisibles en ambas lecturas, justo
 * el dato más reciente y complejo del formulario, S6.1). */
function TaxLinesList({ value }: { value: unknown }) {
  if (!Array.isArray(value)) return null
  if (value.length === 0) {
    return (
      <li>
        <span className="font-medium">tax_lines:</span> sin tramos
      </li>
    )
  }
  return (
    <li>
      <span className="font-medium">tax_lines:</span>
      <ul className="ml-4 list-disc space-y-0.5">
        {value.map((line: Record<string, unknown>, i) => {
          const rate = line.rate ?? line.iva_pct
          return (
            <li key={i}>
              {String(rate ?? '—')}%: base {String(line.base ?? '—')}, cuota{' '}
              {String(line.cuota ?? '—')}
            </li>
          )
        })}
      </ul>
    </li>
  )
}

interface LabDetailProps {
  detail: LabDetail
  onClose: () => void
}

// Panel lateral derecho (2026-08-09, corrección de Julio tras probar la primera versión centrada:
// "en una ventana emergente comprobable o en una sidebar a la derecha, que eso sería incluso
// mejor"), mismo `role="dialog"` que el resto de diálogos del proyecto (fondo oscuro, clic fuera
// cierra), solo cambia la posición/anchura. `LabDetailView` no cambia por dentro: solo se envuelve.
function LabDetailModal({ detail, onClose }: LabDetailProps) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Laboratorio de esta factura"
      className="fixed inset-0 z-50 bg-black/60"
      onClick={onClose}
    >
      <div
        className="ml-auto h-full w-full max-w-2xl overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <LabDetailView detail={detail} onClose={onClose} />
      </div>
    </div>
  )
}

const CORRECTIONS_HEADER_LABELS: Record<string, string> = {
  field: 'Campo',
  ai_value: 'Leído por la IA',
  human_value: 'Guardado por el humano',
}

const RANKING_HEADER_LABELS: Record<string, string> = {
  engine: 'Motor',
  score: 'Puntuación',
}

function LabDetailView({ detail, onClose }: LabDetailProps) {
  const correctionsState = usePersistedTableState('lab-corrections-column-widths')
  const correctionsColumns = useMemo<ColumnDef<Reading3Correction, unknown>[]>(
    () => [
      { id: 'field', header: 'Campo', accessorFn: (r) => r.field, size: 120, minSize: 32 },
      {
        id: 'ai_value',
        header: 'Leído por la IA',
        accessorFn: (r) => r.ai_value ?? undefined,
        size: 140,
        minSize: 32,
        sortUndefined: 'last',
      },
      {
        id: 'human_value',
        header: 'Guardado por el humano',
        accessorFn: (r) => r.human_value ?? undefined,
        size: 160,
        minSize: 32,
        sortUndefined: 'last',
      },
    ],
    [],
  )
  const correctionsTable = useReactTable({
    data: detail.reading_3.corrections,
    columns: correctionsColumns,
    state: {
      columnSizing: correctionsState.columnSizing,
      columnSizingInfo: correctionsState.columnSizingInfo,
      sorting: correctionsState.sorting,
    },
    onColumnSizingChange: correctionsState.onColumnSizingChange,
    onColumnSizingInfoChange: correctionsState.onColumnSizingInfoChange,
    onSortingChange: correctionsState.setSorting,
    columnResizeMode: 'onChange',
    sortDescFirst: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })
  const sortedCorrections = correctionsTable.getRowModel().rows.map((r) => r.original)

  const rankingState = usePersistedTableState('lab-ranking-column-widths')
  const rankingColumns = useMemo<ColumnDef<RankingEntry, unknown>[]>(
    () => [
      { id: 'engine', header: 'Motor', accessorFn: (r) => r.engine, size: 160, minSize: 32 },
      { id: 'score', header: 'Puntuación', accessorFn: (r) => r.score, size: 100, minSize: 32 },
    ],
    [],
  )
  const rankingTable = useReactTable({
    data: detail.ranking,
    columns: rankingColumns,
    state: {
      columnSizing: rankingState.columnSizing,
      columnSizingInfo: rankingState.columnSizingInfo,
      sorting: rankingState.sorting,
    },
    onColumnSizingChange: rankingState.onColumnSizingChange,
    onColumnSizingInfoChange: rankingState.onColumnSizingInfoChange,
    onSortingChange: rankingState.setSorting,
    columnResizeMode: 'onChange',
    sortDescFirst: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })
  const sortedRanking = rankingTable.getRowModel().rows.map((r) => r.original)

  return (
    <div className="min-h-full space-y-6 border-l border-slate-700 bg-slate-800 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Laboratorio de esta factura</h2>
        <button type="button" onClick={onClose} className="text-sm text-slate-400 underline">
          Cerrar
        </button>
      </div>

      <section data-testid="lab-reading-1" className="space-y-2">
        <h3 className="font-semibold text-slate-200">Lectura 1 — lo que leyó la IA</h3>
        {detail.reading_1 ? (
          <>
            {/* N=1 hoy (ADR-0016): el mismo motor produjo todos los campos de esta lectura, se
                muestra así tal cual (spec C7), sin inventar una granularidad por campo que el
                sistema no tiene todavía. */}
            <p className="text-xs text-slate-400">
              Motor: {detail.reading_1.engine} ({detail.reading_1.model})
            </p>
            <pre className="max-h-64 overflow-auto rounded bg-slate-900 p-2 text-xs text-slate-300">
              {JSON.stringify(detail.reading_1.raw, null, 2)}
            </pre>
          </>
        ) : (
          <p className="text-slate-400">Sin lectura cruda disponible para esta factura.</p>
        )}
      </section>

      <section data-testid="lab-reading-2" className="space-y-2">
        <h3 className="font-semibold text-slate-200">
          Lectura 2 — tras los ajustes internos (reglas actuales)
        </h3>
        <p className="text-xs text-slate-500">
          Recalculada ahora mismo con el rol más restrictivo (no necesariamente el rol real de quien
          confirmó en su día): puede mostrar un motivo de bloqueo que en la confirmación real no se
          disparó.
        </p>
        {detail.reading_2 ? (
          <>
            <p className="text-sm text-slate-300">
              Veredicto CIF de contraparte:{' '}
              <span className="font-medium">{detail.reading_2.counterparty_verdict.status}</span>
            </p>
            <p className="text-xs text-slate-400">
              Identidad propia conocida (no leída por IA, ADR-0011): {detail.reading_2.own.name ?? '—'}{' '}
              ({detail.reading_2.own.cif ?? '—'})
            </p>
            <ul className="space-y-1 text-sm text-slate-300">
              {scalarFields(detail.reading_2.fields as unknown as Record<string, unknown>).map(
                ([field, value]) => (
                  <li key={field}>
                    <span className="font-medium">{field}:</span>{' '}
                    {value === null || value === '' ? 'No leído' : String(value)}{' '}
                    <span className="text-xs text-slate-500">
                      (confianza: {detail.reading_2?.confidences[field] ?? 'sin dato'})
                    </span>
                  </li>
                ),
              )}
              <TaxLinesList value={detail.reading_2.fields.tax_lines} />
            </ul>
            {detail.reading_2.blocking_reasons.length > 0 && (
              <p className="text-sm text-red-400">
                Motivos de bloqueo: {detail.reading_2.blocking_reasons.join(', ')}
              </p>
            )}
            {detail.reading_2.warnings.length > 0 && (
              <p className="text-sm text-yellow-400">
                Avisos: {detail.reading_2.warnings.join(', ')}
              </p>
            )}
          </>
        ) : (
          <p className="text-slate-400">Sin lectura disponible para esta factura.</p>
        )}
      </section>

      <section data-testid="lab-reading-3" className="space-y-2">
        <h3 className="font-semibold text-slate-200">Lectura 3 — lo guardado tras tus cambios</h3>
        <ul className="space-y-1 text-sm text-slate-300">
          {scalarFields(detail.reading_3.invoice).map(([field, value]) => (
            <li key={field}>
              <span className="font-medium">{field}:</span> {String(value ?? '—')}
            </li>
          ))}
          <TaxLinesList value={detail.reading_3.invoice.tax_lines} />
        </ul>
        {detail.reading_3.has_corrections ? (
          <table className="whitespace-nowrap text-left text-sm" style={{ tableLayout: 'fixed', width: correctionsTable.getTotalSize() }}>
            <thead className="text-slate-400">
              {correctionsTable.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <DataTableTh
                      key={header.id}
                      header={header}
                      label={CORRECTIONS_HEADER_LABELS[header.id] ?? ''}
                    />
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-slate-800">
              {sortedCorrections.map((c) => (
                <tr key={c.field}>
                  <td className="truncate p-1">{c.field}</td>
                  <td className="truncate p-1">{c.ai_value ?? '—'}</td>
                  <td className="truncate p-1">{c.human_value ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-slate-400">Sin correcciones: el humano confirmó tal cual lo leyó la IA.</p>
        )}
      </section>

      <section data-testid="lab-ranking" className="space-y-2">
        <h3 className="font-semibold text-slate-200">Comparativa de modelos</h3>
        {detail.ranking_available ? (
          <table className="whitespace-nowrap text-left text-sm" style={{ tableLayout: 'fixed', width: rankingTable.getTotalSize() }}>
            <thead className="text-slate-400">
              {rankingTable.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <DataTableTh
                      key={header.id}
                      header={header}
                      label={RANKING_HEADER_LABELS[header.id] ?? ''}
                    />
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-slate-800">
              {sortedRanking.map((row) => (
                <tr key={row.engine}>
                  <td className="truncate p-1">{row.engine}</td>
                  <td className="truncate p-1">{row.score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-slate-400">
            Sin datos de comparativa para esta factura (el experimento no estaba encendido cuando
            se procesó).
          </p>
        )}
      </section>
    </div>
  )
}

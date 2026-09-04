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
import { useMemo, useRef, useState } from 'react'

import { DataTableTh } from '../../shared/DataTableTh'
import { formatCurrency, formatDateTime } from '../../shared/format'
import { usePersistedTableState } from '../../shared/usePersistedTableState'
import { InvoiceImageModal } from '../panel/InvoiceImageModal'
import { useSession } from '../session/SessionProvider'
import type { FieldComparison, LabDetail, LabInvoiceRow, TaxLineDict } from './labTypes'
import { useInvoiceLab } from './useInvoiceLab'
import { useBenchmarkRanking } from './useBenchmarkRanking'
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
  const imageRequestRef = useRef(0)

  const isAdminTech = user?.is_admin_tech ?? false
  const tenants = useTenants(isAdminTech)
  const invoices = useTenantInvoices(isAdminTech ? tenantId : null)
  const lab = useInvoiceLab(isAdminTech ? tenantId : null, labFileId)
  const benchmark = useBenchmarkRanking(isAdminTech)
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
    const request = ++imageRequestRef.current
    image.mutate({ tenantId, fileId }, {
      onSuccess: (url) => {
        if (imageRequestRef.current !== request) {
          URL.revokeObjectURL(url)
          return
        }
        setImageUrl(url)
      },
    })
  }

  const closeImage = () => {
    imageRequestRef.current += 1
    if (imageUrl) URL.revokeObjectURL(imageUrl)
    setImageUrl(null)
    image.reset()
  }

  const closeLab = () => {
    closeImage()
    setLabFileId(null)
  }

  if (labFileId) {
    return (
      <section className="tn-panel-page mx-auto max-w-6xl space-y-6 p-6">
        <button type="button" onClick={closeLab} className="text-sm text-emerald-400 underline">
          Volver al resumen
        </button>
        <h1 className="text-xl font-semibold">Factura en laboratorio</h1>
        {lab.isLoading && <p className="text-slate-400">Cargando laboratorio…</p>}
        {lab.isError && (
          <p role="alert" className="text-red-400">
            No se pudo cargar el laboratorio de esta factura.
          </p>
        )}
        {lab.data && (
          <LabDetailView
            detail={lab.data}
            imageUrl={imageUrl}
            imageLoading={image.isPending}
            imageError={image.isError}
            onLoadImage={() => handleView(labFileId)}
          />
        )}
      </section>
    )
  }

  return (
    <section className="tn-panel-page mx-auto max-w-5xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Laboratorio OCR</h1>
      <p className="text-sm text-slate-400">
        Diagnóstico por factura: Lectura 1 (lo que leyó la IA), Lectura 2 (tras los ajustes
        internos), Lectura 3 (lo guardado tras tus cambios) y la comparativa de modelos. Solo
        lectura, herramienta interna temporal.
      </p>

      <BenchmarkSummary ranking={benchmark.data} isLoading={benchmark.isLoading} isError={benchmark.isError} />

      <label className="flex max-w-xs flex-col gap-1 text-sm text-slate-300">
        Tenant
        <select
          aria-label="Tenant"
          value={tenantId ?? ''}
          onChange={(e) => {
            closeImage()
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
                      Abrir laboratorio
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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

type BenchmarkRankingData = NonNullable<ReturnType<typeof useBenchmarkRanking>['data']>
type FieldGroupRow = BenchmarkRankingData['by_field_group'][number]
type CombinationRow = BenchmarkRankingData['by_combination'][number]

function combinationKey(variant: string, engine: string) {
  return `${variant}:${engine}`
}

function ratioLabel(ratio: number | null) {
  return ratio === null ? 'Sin datos comparables todavía' : `${Math.round(ratio * 100)}%`
}

function BenchmarkSummary({
  ranking,
  isLoading,
  isError,
}: {
  ranking: BenchmarkRankingData | undefined
  isLoading: boolean
  isError: boolean
}) {
  const [selectedField, setSelectedField] = useState('Todos los campos')
  const fieldRows = ranking?.by_field_group ?? []
  const combinations = ranking?.by_combination ?? []
  const fields = [...new Set(fieldRows.map((row) => row.field_group))]
  const displayed: Array<FieldGroupRow | (CombinationRow & { ratio: number | null })> =
    selectedField === 'Todos los campos'
      ? combinations.map((row) => ({ ...row, ratio: row.comparables === 0 ? null : row.aciertos / row.comparables }))
      : fieldRows.filter((row) => row.field_group === selectedField)
  const errors = new Map(combinations.map((row) => [combinationKey(row.variant, row.engine), row.errors]))
  const engines = [...new Set(combinations.map((row) => row.engine))]
  const variants = ['original', 'enhanced', 'clahe']

  if (isLoading) return <p className="text-slate-400">Cargando comparativa real…</p>
  if (isError) return <p role="alert" className="text-red-400">No se pudo cargar la comparativa real.</p>
  if (!ranking || (fieldRows.length === 0 && combinations.length === 0)) {
    return <p className="text-slate-400">Todavía no hay resultados. Lanza el lote desde Ranking OCR.</p>
  }

  return (
    <section className="space-y-4 rounded-lg border border-slate-800 p-4">
      <div>
        <h2 className="font-semibold">Resumen de rendimiento real</h2>
        <p className="text-sm text-slate-400">Solo resultados persistidos contra facturas confirmadas.</p>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Filtrar por campo">
        {['Todos los campos', ...fields].map((field) => (
          <button
            key={field}
            type="button"
            onClick={() => setSelectedField(field)}
            aria-pressed={selectedField === field}
            className="rounded-full border border-slate-600 px-3 py-1 text-sm aria-pressed:border-emerald-500 aria-pressed:bg-emerald-600"
          >
            {field}
          </button>
        ))}
      </div>
      {fields.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {fields.map((field) => {
            const rows = fieldRows.filter((row) => row.field_group === field)
            const bestRatio = Math.max(...rows.map((row) => row.ratio ?? -1))
            const winners = rows.filter((row) => row.ratio === bestRatio && row.ratio !== null)
            return (
              <article key={field} className="rounded border border-slate-700 p-3 text-sm">
                <h3 className="font-medium">{field}</h3>
                {winners.length === 0 ? (
                  <p className="mt-1 text-slate-400">Sin datos comparables todavía.</p>
                ) : (
                  winners.map((winner) => (
                    <p key={combinationKey(winner.variant, winner.engine)} className="mt-1 text-emerald-400">
                      {winner.engine} ({winner.variant}): {winner.aciertos}/{winner.comparables}
                    </p>
                  ))
                )}
              </article>
            )
          })}
        </div>
      )}
      <div data-testid="benchmark-heatmap" className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-slate-400">
            <tr>
              <th className="p-2">Motor</th>
              {variants.map((variant) => <th key={variant} className="p-2">{variant}</th>)}
            </tr>
          </thead>
          <tbody>
            {engines.map((engine) => (
              <tr key={engine} className="border-t border-slate-800">
                <th className="p-2 font-medium">{engine}</th>
                {variants.map((variant) => {
                  const row = displayed.find((entry) => entry.engine === engine && entry.variant === variant)
                  const errorCount = errors.get(combinationKey(variant, engine)) ?? 0
                  return (
                    <td key={variant} className="p-2">
                      {!row && errorCount > 0 ? (
                        <span className="text-slate-400">Sin datos comparables todavía · {errorCount} errores</span>
                      ) : !row ? '—' : (
                        <span className={row.ratio === null ? 'text-slate-400' : row.ratio >= 0.8 ? 'text-emerald-400' : 'text-amber-400'}>
                          {ratioLabel(row.ratio)} · {row.comparables} comparables{errorCount > 0 ? ` · ${errorCount} errores` : ''}
                        </span>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {combinations.some((row) => row.errors > 0) && (
        <p className="text-sm text-amber-400">
          {combinations
            .filter((row) => row.errors > 0)
            .map((row) => `${row.engine}: ${row.errors} errores`)
            .join(' · ')}
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
  imageUrl?: string | null
  imageLoading?: boolean
  imageError?: boolean
  onLoadImage?: () => void
}

// S6.6 Área B: nombres de dominio (`invoicing`) traducidos a etiqueta legible. Un campo sin
// etiqueta (no debería ocurrir con los 7 campos reales del backend, spec C10) cae a su propio
// nombre — igual de criterio que el resto de tablas del proyecto (`INVOICE_HEADER_LABELS`).
const FIELD_LABELS: Record<string, string> = {
  counterparty_tax_id: 'CIF contraparte',
  counterparty_name: 'Nombre contraparte',
  invoice_number: 'Número de factura',
  issue_date: 'Fecha',
  net_amount: 'Base imponible',
  tax_amount: 'Cuota IVA',
  total_amount: 'Total',
}

const FIELD_COMPARISON_HEADER_LABELS: Record<string, string> = {
  field: 'Campo',
  column_2: 'Decidió el sistema',
  column_3: 'Confirmado',
  match: 'Acierto',
}

/** Badge de acierto (S6.6 C6-C8): verde si coinciden, rojo si no, gris neutro si no es comparable
 * (columna 3 nula) — nunca rojo ni verde sin una verdad confirmada con la que comparar. */
function MatchBadge({ match }: { match: boolean | null }) {
  if (match === null) {
    return (
      <span className="text-slate-500" aria-label="no comparable">
        —
      </span>
    )
  }
  return match ? (
    <span className="text-emerald-400" aria-label="acierto">
      ✓✓
    </span>
  ) : (
    <span className="text-red-400" aria-label="fallo">
      ✗
    </span>
  )
}

function formatTaxLineDicts(lines: TaxLineDict[]): string {
  if (lines.length === 0) return 'sin tramos'
  return lines.map((l) => `${l.iva_pct}%: base ${l.base}, cuota ${l.cuota}`).join('; ')
}

function matchSortKey(match: boolean | null): string {
  if (match === null) return 'b-neutro'
  return match ? 'a-acierto' : 'c-fallo'
}

function LabDetailView({ detail, imageUrl, imageLoading = false, imageError = false, onLoadImage }: LabDetailProps) {
  const [section, setSection] = useState<'photo' | 'reading-1' | 'reading-2' | 'reading-3' | 'ranking'>('reading-1')
  const [benchmarkField, setBenchmarkField] = useState('Todos los campos')
  const fieldComparisonState = usePersistedTableState('lab-field-comparison-column-widths')
  const fieldComparisonColumns = useMemo<ColumnDef<FieldComparison, unknown>[]>(
    () => [
      { id: 'field', header: 'Campo', accessorFn: (r) => FIELD_LABELS[r.field] ?? r.field, size: 150, minSize: 32 },
      {
        id: 'column_2',
        header: 'Decidió el sistema',
        accessorFn: (r) => r.column_2 ?? undefined,
        size: 150,
        minSize: 32,
        sortUndefined: 'last',
      },
      {
        id: 'column_3',
        header: 'Confirmado',
        accessorFn: (r) => r.column_3 ?? undefined,
        size: 150,
        minSize: 32,
        sortUndefined: 'last',
      },
      { id: 'match', header: 'Acierto', accessorFn: (r) => matchSortKey(r.match), size: 90, minSize: 32 },
    ],
    [],
  )
  const fieldComparisonTable = useReactTable({
    data: detail.reading_3.field_comparison,
    columns: fieldComparisonColumns,
    state: {
      columnSizing: fieldComparisonState.columnSizing,
      columnSizingInfo: fieldComparisonState.columnSizingInfo,
      sorting: fieldComparisonState.sorting,
    },
    onColumnSizingChange: fieldComparisonState.onColumnSizingChange,
    onColumnSizingInfoChange: fieldComparisonState.onColumnSizingInfoChange,
    onSortingChange: fieldComparisonState.setSorting,
    columnResizeMode: 'onChange',
    sortDescFirst: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })
  const sortedFieldComparison = fieldComparisonTable.getRowModel().rows.map((r) => r.original)

  const benchmarkFields = [
    ...new Set([
      ...detail.ranking.flatMap((entry) => entry.field_results.map((result) => result.field)),
      'tax_lines',
    ]),
  ]
  const benchmarkEngines = [...new Set(detail.ranking.map((entry) => entry.engine))].sort()
  const benchmarkVariants = ['original', 'enhanced', 'clahe']

  return (
    <div className="min-h-full space-y-6 bg-slate-800 p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Diagnóstico de factura</h2>
      </div>
      <div className="flex flex-wrap gap-2" aria-label="Sección del diagnóstico">
        {[
          ['photo', 'Foto'],
          ['reading-1', 'Lectura 1'],
          ['reading-2', 'Lectura 2'],
          ['reading-3', 'Lectura 3'],
          ['ranking', 'Comparativa IA'],
        ].map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setSection(id as typeof section)}
            aria-pressed={section === id}
            className="rounded-full border border-slate-600 px-3 py-1 text-sm aria-pressed:border-emerald-500 aria-pressed:bg-emerald-600"
          >
            {label}
          </button>
        ))}
      </div>

      {section === 'photo' && (
        <section className="space-y-3">
          <h3 className="font-semibold text-slate-200">Foto original</h3>
          {!imageUrl && !imageLoading && !imageError && (
            <button type="button" onClick={onLoadImage} className="rounded border border-slate-600 px-3 py-2 text-sm text-slate-100">
              Cargar foto
            </button>
          )}
          {imageLoading && <p className="text-slate-400">Cargando foto…</p>}
          {imageError && <p role="alert" className="text-red-400">No se pudo cargar la imagen de la factura.</p>}
          {imageUrl && <img src={imageUrl} alt="Factura original" className="max-h-[70vh] max-w-full rounded border border-slate-700" />}
        </section>
      )}

      {section === 'reading-1' && <section data-testid="lab-reading-1" className="space-y-2">
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
      </section>}

      {section === 'reading-2' && <section data-testid="lab-reading-2" className="space-y-2">
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
      </section>}

      {section === 'reading-3' && <section data-testid="lab-reading-3" className="space-y-2">
        <h3 className="font-semibold text-slate-200">Lectura 3 — lo guardado tras tus cambios</h3>
        <ul className="space-y-1 text-sm text-slate-300">
          {scalarFields(detail.reading_3.invoice).map(([field, value]) => (
            <li key={field}>
              <span className="font-medium">{field}:</span> {String(value ?? '—')}
            </li>
          ))}
          <TaxLinesList value={detail.reading_3.invoice.tax_lines} />
        </ul>
        {/* S6.6 C10/C11: la tabla se pinta SIEMPRE, con los 7 campos + tramos de IVA, tenga o no
            correcciones — el propio contenido (todo verde) ya comunica "sin correcciones" con más
            detalle que el mensaje aparte que tenía S6.2. */}
        <table
          className="whitespace-nowrap text-left text-sm"
          style={{ tableLayout: 'fixed', width: fieldComparisonTable.getTotalSize() }}
        >
          <thead className="text-slate-400">
            {fieldComparisonTable.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <DataTableTh
                    key={header.id}
                    header={header}
                    label={FIELD_COMPARISON_HEADER_LABELS[header.id] ?? ''}
                  />
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-slate-800">
            {sortedFieldComparison.map((f) => (
              <tr key={f.field} className={f.match === false ? 'bg-red-950/40' : undefined}>
                <td className="truncate p-1">{FIELD_LABELS[f.field] ?? f.field}</td>
                <td className="truncate p-1">{f.column_2 ?? '—'}</td>
                <td className="truncate p-1">{f.column_3 ?? '—'}</td>
                <td className="truncate p-1">
                  <MatchBadge match={f.match} />
                </td>
              </tr>
            ))}
            {/* S6.6 C9: tramos de IVA, fila manual (no encaja en el bucle de campos escalares de
                arriba, no participa del orden de la tabla). */}
            <tr
              className={
                detail.reading_3.tax_lines_comparison.match === false ? 'bg-red-950/40' : undefined
              }
            >
              <td className="truncate p-1">Tramos de IVA</td>
              <td className="truncate p-1">
                {formatTaxLineDicts(detail.reading_3.tax_lines_comparison.column_2)}
              </td>
              <td className="truncate p-1">
                {formatTaxLineDicts(detail.reading_3.tax_lines_comparison.column_3)}
              </td>
              <td className="truncate p-1">
                <MatchBadge match={detail.reading_3.tax_lines_comparison.match} />
              </td>
            </tr>
          </tbody>
        </table>
      </section>}

      {section === 'ranking' && <section data-testid="lab-ranking" className="space-y-2">
        <h3 className="font-semibold text-slate-200">Comparativa real de variantes y modelos</h3>
        {detail.ranking_available ? (
          <>
            <div className="flex flex-wrap gap-2" aria-label="Campo de la comparativa">
              {['Todos los campos', ...benchmarkFields].map((field) => (
                <button
                  key={field}
                  type="button"
                  onClick={() => setBenchmarkField(field)}
                  aria-pressed={benchmarkField === field}
                  className="rounded-full border border-slate-600 px-3 py-1 text-sm aria-pressed:border-emerald-500 aria-pressed:bg-emerald-600"
                >
                  {FIELD_LABELS[field] ?? (field === 'tax_lines' ? 'Tramos IVA' : field)}
                </button>
              ))}
            </div>
            <div data-testid="lab-ranking-scroll" className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-slate-400">
                  <tr>
                    <th className="p-2">Motor</th>
                    {benchmarkVariants.map((variant) => <th key={variant} className="p-2">{variant}</th>)}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {benchmarkEngines.map((engine) => (
                    <tr key={engine}>
                      <th className="p-2 text-left font-medium">{engine}</th>
                      {benchmarkVariants.map((variant) => {
                        const entry = detail.ranking.find((candidate) => candidate.engine === engine && candidate.variant === variant)
                        const results = entry
                          ? [...entry.field_results, { field: 'tax_lines', match: entry.tax_lines_matched }]
                              .filter((result) => benchmarkField === 'Todos los campos' || result.field === benchmarkField)
                          : []
                        return (
                          <td key={variant} className="p-2">
                            {!entry ? 'Sin resultado' : results.map((result) => (
                              <span key={result.field} className="mr-2 inline-flex gap-1">
                                {benchmarkField === 'Todos los campos' && `${FIELD_LABELS[result.field] ?? (result.field === 'tax_lines' ? 'Tramos IVA' : result.field)} `}
                                <MatchBadge match={result.match} />
                              </span>
                            ))}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="text-slate-400">
            Sin datos de comparativa para esta factura (el experimento no estaba encendido cuando
            se procesó).
          </p>
        )}
      </section>}
    </div>
  )
}

// Panel de plataforma (S4.1): alta de tenants + listado de los ya existentes. Primera pantalla del
// módulo `platform_admin`; exclusiva del rol `platform_admin` (portero en el backend, aquí no se
// repite esa comprobación, mismo criterio que el resto de pantallas de gestión del proyecto).
// Modo demo (S4.4) + dominios propios (S4.6, alcance acotado — ver
// docs/specs/S4.6-dominios-propios.md §0, columna de solo lectura, sin formulario de edición
// todavía) + ciclo de vida (S4.7: suspender/reactivar/exportar/borrar). Las acciones por fila viven
// en `TenantRowActions` (extraído tras la auditoría de S4.7: la celda había crecido demasiado
// mezclando 4 flujos de mutación distintos).
//
// Las dos tablas (tenants + métricas) son redimensionables/ordenables (2026-08-10, "todas las
// tablas de todas las URL"), mismo mecanismo que `CompaniesPanel`/`InvoicesPanel`.
import { getCoreRowModel, getSortedRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { useMemo, useState, type ChangeEvent, type FormEvent } from 'react'

import { DataTableTh } from '../../shared/DataTableTh'
import { formatDate, formatDateTime } from '../../shared/format'
import { ScrollableTable } from '../../shared/ScrollableTable'
import { usePersistedTableState } from '../../shared/usePersistedTableState'
import { MutationErrorBanner } from './MutationErrorBanner'
import { TenantRowActions } from './TenantRowActions'
import { useCreateTenant } from './useCreateTenant'
import { useTenantMetrics } from './useTenantMetrics'
import { useTenants } from './useTenants'
import { useUploadLogo } from './useUploadLogo'

type TenantRow = NonNullable<ReturnType<typeof useTenants>['data']>[number]
type MetricsRow = NonNullable<ReturnType<typeof useTenantMetrics>['data']>[number]

const TENANT_HEADER_LABELS: Record<string, string> = {
  slug: 'Subdominio',
  name: 'Nombre',
  status: 'Estado',
  is_demo: 'Demo',
  created_at: 'Alta',
}

const METRICS_HEADER_LABELS: Record<string, string> = {
  slug: 'Subdominio',
  companies_count: 'Empresas',
  users_count: 'Usuarios',
  admins_count: 'Admins',
  invoices_this_month: 'Facturas este mes',
  invoices_total_count: 'Facturas totales',
  ocr_extractions_count: 'Facturas procesadas (OCR)',
  last_activity_at: 'Último uso',
}

const EMPTY_FORM = {
  name: '',
  slug: '',
  logo_url: '',
  color_primary: '',
  color_secondary: '',
  is_demo: false,
}

export function PlatformTenants() {
  const tenants = useTenants()
  const metrics = useTenantMetrics()
  const createTenant = useCreateTenant()
  const uploadLogo = useUploadLogo()
  const [form, setForm] = useState(EMPTY_FORM)

  const rows = useMemo(() => tenants.data ?? [], [tenants.data])
  const tenantsTableState = usePersistedTableState('platform-tenants-column-widths')
  const tenantColumns = useMemo<ColumnDef<TenantRow, unknown>[]>(
    () => [
      { id: 'slug', header: 'Subdominio', accessorFn: (r) => r.slug, size: 140, minSize: 32 },
      { id: 'name', header: 'Nombre', accessorFn: (r) => r.name, size: 160, minSize: 32 },
      { id: 'status', header: 'Estado', accessorFn: (r) => r.status, size: 100, minSize: 32 },
      { id: 'is_demo', header: 'Demo', accessorFn: (r) => (r.is_demo ? 1 : 0), size: 70, minSize: 32 },
      { id: 'created_at', header: 'Alta', accessorFn: (r) => r.created_at, size: 110, minSize: 32 },
      { id: 'actions', header: 'Acciones', size: 220, enableSorting: false, enableResizing: false },
    ],
    [],
  )
  const tenantsTable = useReactTable({
    data: rows,
    columns: tenantColumns,
    state: {
      columnSizing: tenantsTableState.columnSizing,
      columnSizingInfo: tenantsTableState.columnSizingInfo,
      sorting: tenantsTableState.sorting,
    },
    onColumnSizingChange: tenantsTableState.onColumnSizingChange,
    onColumnSizingInfoChange: tenantsTableState.onColumnSizingInfoChange,
    onSortingChange: tenantsTableState.setSorting,
    columnResizeMode: 'onChange',
    sortDescFirst: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })
  const sortedTenantRows = tenantsTable.getRowModel().rows.map((r) => r.original)

  const metricsRows = useMemo(() => metrics.data ?? [], [metrics.data])
  const metricsTableState = usePersistedTableState('platform-tenant-metrics-column-widths')
  const metricsColumns = useMemo<ColumnDef<MetricsRow, unknown>[]>(
    () => [
      { id: 'slug', header: 'Subdominio', accessorFn: (r) => r.slug, size: 140, minSize: 32 },
      {
        id: 'companies_count',
        header: 'Empresas',
        accessorFn: (r) => r.companies_count,
        size: 90,
        minSize: 32,
      },
      { id: 'users_count', header: 'Usuarios', accessorFn: (r) => r.users_count, size: 90, minSize: 32 },
      { id: 'admins_count', header: 'Admins', accessorFn: (r) => r.admins_count, size: 90, minSize: 32 },
      {
        id: 'invoices_this_month',
        header: 'Facturas este mes',
        accessorFn: (r) => r.invoices_this_month,
        size: 140,
        minSize: 32,
      },
      {
        id: 'invoices_total_count',
        header: 'Facturas totales',
        accessorFn: (r) => r.invoices_total_count,
        size: 130,
        minSize: 32,
      },
      {
        id: 'ocr_extractions_count',
        header: 'Facturas procesadas (OCR)',
        accessorFn: (r) => r.ocr_extractions_count,
        size: 180,
        minSize: 32,
      },
      {
        id: 'last_activity_at',
        header: 'Último uso',
        accessorFn: (r) => r.last_activity_at ?? undefined,
        size: 140,
        minSize: 32,
        sortUndefined: 'last',
      },
    ],
    [],
  )
  const metricsTable = useReactTable({
    data: metricsRows,
    columns: metricsColumns,
    state: {
      columnSizing: metricsTableState.columnSizing,
      columnSizingInfo: metricsTableState.columnSizingInfo,
      sorting: metricsTableState.sorting,
    },
    onColumnSizingChange: metricsTableState.onColumnSizingChange,
    onColumnSizingInfoChange: metricsTableState.onColumnSizingInfoChange,
    onSortingChange: metricsTableState.setSorting,
    columnResizeMode: 'onChange',
    sortDescFirst: false,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })
  const sortedMetricsRows = metricsTable.getRowModel().rows.map((r) => r.original)

  const handleLogoFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = '' // permite volver a elegir el mismo fichero si la subida falla
    if (!file) return
    uploadLogo.mutate(file, {
      onSuccess: (data) => setForm((f) => ({ ...f, logo_url: data.logo_url })),
    })
  }

  const handleCreate = (e: FormEvent) => {
    e.preventDefault()
    createTenant.mutate(
      {
        name: form.name,
        slug: form.slug,
        logo_url: form.logo_url === '' ? null : form.logo_url,
        color_primary: form.color_primary === '' ? null : form.color_primary,
        color_secondary: form.color_secondary === '' ? null : form.color_secondary,
        is_demo: form.is_demo,
      },
      { onSuccess: () => setForm(EMPTY_FORM) },
    )
  }

  return (
    <section className="tn-panel-page mx-auto max-w-4xl space-y-8 p-6">
      <div>
        <h1 className="text-xl font-semibold">Plataforma — Asesorías</h1>

        <form onSubmit={handleCreate} className="mt-3 flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-sm text-slate-300">
            Nombre
            <input
              required
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
            />
          </label>
          <label className="flex flex-col text-sm text-slate-300">
            Subdominio
            <input
              required
              value={form.slug}
              onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
            />
          </label>
          <div className="flex flex-col gap-1 text-sm text-slate-300">
            <div className="flex items-end gap-2">
              <label className="flex flex-col">
                Logo (URL)
                <input
                  value={form.logo_url}
                  onChange={(e) => setForm((f) => ({ ...f, logo_url: e.target.value }))}
                  className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
                />
              </label>
              {/* Alternativa a pegar una URL ya alojada en otro sitio (2026-08-01, decisión de
                  Julio): sube la imagen y rellena el campo de arriba con la URL pública real.
                  Hermano del `label` de arriba, nunca anidado dentro (un `<label>` dentro de otro
                  `<label>` es HTML inválido y rompe la asociación accesible del primero). */}
              <label className="cursor-pointer rounded border border-slate-600 px-2 py-1 text-xs text-slate-100">
                {uploadLogo.isPending ? 'Subiendo…' : 'Subir imagen'}
                <input
                  type="file"
                  accept="image/png,image/jpeg"
                  onChange={handleLogoFileChange}
                  disabled={uploadLogo.isPending}
                  className="sr-only"
                />
              </label>
            </div>
            {uploadLogo.isError && (
              <p role="alert" className="text-xs text-red-400">
                {uploadLogo.error instanceof Error ? uploadLogo.error.message : 'No se pudo subir el logo.'}
              </p>
            )}
          </div>
          <label className="flex flex-col text-sm text-slate-300">
            Color primario
            <input
              type="text"
              placeholder="#112233"
              value={form.color_primary}
              onChange={(e) => setForm((f) => ({ ...f, color_primary: e.target.value }))}
              className="w-28 rounded border border-slate-600 bg-slate-800 px-2 py-1"
            />
          </label>
          <label className="flex flex-col text-sm text-slate-300">
            Color secundario
            <input
              type="text"
              placeholder="#445566"
              value={form.color_secondary}
              onChange={(e) => setForm((f) => ({ ...f, color_secondary: e.target.value }))}
              className="w-28 rounded border border-slate-600 bg-slate-800 px-2 py-1"
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={form.is_demo}
              onChange={(e) => setForm((f) => ({ ...f, is_demo: e.target.checked }))}
            />
            Es demo
          </label>
          <button
            type="submit"
            disabled={createTenant.isPending}
            className="rounded-md border border-slate-600 px-4 py-2 text-slate-100 disabled:opacity-40"
          >
            {createTenant.isPending ? 'Creando…' : 'Nuevo tenant'}
          </button>
        </form>
        <MutationErrorBanner mutation={createTenant} fallback="No se pudo crear el tenant." />
      </div>

      {tenants.isLoading && <p className="text-slate-400">Cargando…</p>}

      {tenants.isError && (
        <p role="alert" className="text-red-400">
          No se pudieron cargar los tenants. Inténtalo de nuevo.
        </p>
      )}

      {!tenants.isLoading && !tenants.isError && rows.length === 0 && (
        <p className="text-slate-400">Todavía no hay tenants.</p>
      )}

      {!tenants.isLoading && !tenants.isError && rows.length > 0 && (
        <ScrollableTable>
          <table
            className="whitespace-nowrap text-left text-sm"
            style={{ tableLayout: 'fixed', width: tenantsTable.getTotalSize() }}
            data-testid="tenants-table"
          >
            <thead className="text-slate-400">
              {tenantsTable.getHeaderGroups().map((headerGroup) => (
                <tr key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <DataTableTh
                      key={header.id}
                      header={header}
                      label={TENANT_HEADER_LABELS[header.id] ?? ''}
                    />
                  ))}
                </tr>
              ))}
            </thead>
            <tbody className="divide-y divide-slate-700">
              {sortedTenantRows.map((tenant) => (
                <tr key={tenant.id} data-testid="tenant-row">
                  <td className="truncate p-2">{tenant.slug}</td>
                  <td className="truncate p-2">{tenant.name}</td>
                  <td className="truncate p-2">{tenant.status === 'active' ? 'Activo' : 'Suspendido'}</td>
                  <td className="truncate p-2">{tenant.is_demo ? 'Sí' : 'No'}</td>
                  <td className="truncate p-2">{formatDate(tenant.created_at)}</td>
                  <td className="truncate p-2">
                    <TenantRowActions tenant={tenant} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </ScrollableTable>
      )}

      <div>
        <h2 className="text-lg font-semibold">Métricas y consumo</h2>

        {metrics.isLoading && <p className="text-slate-400">Cargando…</p>}

        {metrics.isError && (
          <p role="alert" className="text-red-400">
            No se pudieron cargar las métricas. Inténtalo de nuevo.
          </p>
        )}

        {!metrics.isLoading && !metrics.isError && (
          <ScrollableTable>
            <table
              className="whitespace-nowrap text-left text-sm"
              style={{ tableLayout: 'fixed', width: metricsTable.getTotalSize() }}
              data-testid="tenant-metrics-table"
            >
              <thead className="text-slate-400">
                {metricsTable.getHeaderGroups().map((headerGroup) => (
                  <tr key={headerGroup.id}>
                    {headerGroup.headers.map((header) => (
                      <DataTableTh
                        key={header.id}
                        header={header}
                        label={METRICS_HEADER_LABELS[header.id] ?? ''}
                      />
                    ))}
                  </tr>
                ))}
              </thead>
              <tbody className="divide-y divide-slate-700">
                {sortedMetricsRows.map((row) => (
                  <tr key={row.tenant_id} data-testid="tenant-metrics-row">
                    <td className="truncate p-2">{row.slug}</td>
                    <td className="truncate p-2">{row.companies_count}</td>
                    <td className="truncate p-2">{row.users_count}</td>
                    <td className="truncate p-2">{row.admins_count}</td>
                    <td className="truncate p-2">{row.invoices_this_month}</td>
                    <td className="truncate p-2">{row.invoices_total_count}</td>
                    <td className="truncate p-2">{row.ocr_extractions_count}</td>
                    <td className="truncate p-2">{formatDateTime(row.last_activity_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </ScrollableTable>
        )}
      </div>
    </section>
  )
}

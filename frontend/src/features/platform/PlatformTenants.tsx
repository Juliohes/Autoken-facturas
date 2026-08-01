// Panel de plataforma (S4.1): alta de tenants + listado de los ya existentes. Primera pantalla del
// módulo `platform_admin`; exclusiva del rol `platform_admin` (portero en el backend, aquí no se
// repite esa comprobación, mismo criterio que el resto de pantallas de gestión del proyecto).
// Modo demo (S4.4) + dominios propios (S4.6, alcance acotado — ver
// docs/specs/S4.6-dominios-propios.md §0, columna de solo lectura, sin formulario de edición
// todavía) + ciclo de vida (S4.7: suspender/reactivar/exportar/borrar). Las acciones por fila viven
// en `TenantRowActions` (extraído tras la auditoría de S4.7: la celda había crecido demasiado
// mezclando 4 flujos de mutación distintos).
import { useState, type FormEvent } from 'react'

import { formatDate, formatDateTime } from '../../shared/format'
import { MutationErrorBanner } from './MutationErrorBanner'
import { TenantRowActions } from './TenantRowActions'
import { useCreateTenant } from './useCreateTenant'
import { useTenantMetrics } from './useTenantMetrics'
import { useTenants } from './useTenants'

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
  const [form, setForm] = useState(EMPTY_FORM)

  const rows = tenants.data ?? []

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
    <section className="mx-auto max-w-4xl space-y-8 p-6 text-slate-100">
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
          <label className="flex flex-col text-sm text-slate-300">
            Logo (URL)
            <input
              value={form.logo_url}
              onChange={(e) => setForm((f) => ({ ...f, logo_url: e.target.value }))}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
            />
          </label>
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
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" data-testid="tenants-table">
            <thead className="text-slate-400">
              <tr>
                <th className="p-2">Subdominio</th>
                <th className="p-2">Nombre</th>
                <th className="p-2">Estado</th>
                <th className="p-2">Demo</th>
                <th className="p-2">Alta</th>
                <th className="p-2">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {rows.map((tenant) => (
                <tr key={tenant.id} data-testid="tenant-row">
                  <td className="p-2">{tenant.slug}</td>
                  <td className="p-2">{tenant.name}</td>
                  <td className="p-2">{tenant.status === 'active' ? 'Activo' : 'Suspendido'}</td>
                  <td className="p-2">{tenant.is_demo ? 'Sí' : 'No'}</td>
                  <td className="p-2">{formatDate(tenant.created_at)}</td>
                  <td className="p-2">
                    <TenantRowActions tenant={tenant} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" data-testid="tenant-metrics-table">
              <thead className="text-slate-400">
                <tr>
                  <th className="p-2">Subdominio</th>
                  <th className="p-2">Empresas</th>
                  <th className="p-2">Usuarios</th>
                  <th className="p-2">Admins</th>
                  <th className="p-2">Facturas este mes</th>
                  <th className="p-2">Facturas totales</th>
                  <th className="p-2">Facturas procesadas (OCR)</th>
                  <th className="p-2">Último uso</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {(metrics.data ?? []).map((row) => (
                  <tr key={row.tenant_id} data-testid="tenant-metrics-row">
                    <td className="p-2">{row.slug}</td>
                    <td className="p-2">{row.companies_count}</td>
                    <td className="p-2">{row.users_count}</td>
                    <td className="p-2">{row.admins_count}</td>
                    <td className="p-2">{row.invoices_this_month}</td>
                    <td className="p-2">{row.invoices_total_count}</td>
                    <td className="p-2">{row.ocr_extractions_count}</td>
                    <td className="p-2">{formatDateTime(row.last_activity_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  )
}

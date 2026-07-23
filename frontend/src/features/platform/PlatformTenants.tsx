// Panel de plataforma (S4.1): alta de tenants + listado de los ya existentes. Primera pantalla del
// módulo `platform_admin`; exclusiva del rol `platform_admin` (portero en el backend, aquí no se
// repite esa comprobación, mismo criterio que el resto de pantallas de gestión del proyecto).
import { useState, type FormEvent } from 'react'

import { useCreateTenant } from './useCreateTenant'
import { useTenants } from './useTenants'

const EMPTY_FORM = { name: '', slug: '', logo_url: '', color_primary: '', color_secondary: '' }

export function PlatformTenants() {
  const tenants = useTenants()
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
          <button
            type="submit"
            disabled={createTenant.isPending}
            className="rounded-md border border-slate-600 px-4 py-2 text-slate-100 disabled:opacity-40"
          >
            {createTenant.isPending ? 'Creando…' : 'Nuevo tenant'}
          </button>
        </form>
        {createTenant.isError && (
          <p role="alert" className="mt-2 text-sm text-red-400">
            {createTenant.error instanceof Error
              ? createTenant.error.message
              : 'No se pudo crear el tenant.'}
          </p>
        )}
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
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {rows.map((tenant) => (
                <tr key={tenant.id} data-testid="tenant-row">
                  <td className="p-2">{tenant.slug}</td>
                  <td className="p-2">{tenant.name}</td>
                  <td className="p-2">{tenant.status === 'active' ? 'Activo' : 'Suspendido'}</td>
                  <td className="p-2">{tenant.is_demo ? 'Sí' : 'No'}</td>
                  <td className="p-2">{tenant.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

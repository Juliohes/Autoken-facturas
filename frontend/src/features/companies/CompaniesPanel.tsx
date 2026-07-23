// Pantalla "Empresas" de la asesoría (S3.4): ficha agregada (contadores) + alta/edición/borrado
// (reutiliza el CRUD de S1.5 tal cual) + registros pendientes (reutiliza S1.4 tal cual). Solo
// `tenant_admin` la ve (portero de roles en el backend; aquí no se repite esa comprobación).
import { useState, type FormEvent } from 'react'

import { CompanyTableRow } from './CompanyTableRow'
import { PendingRegistrations } from './PendingRegistrations'
import { PurgeTestInvoices } from './PurgeTestInvoices'
import { useCompaniesPanel } from './useCompaniesPanel'
import { useCreateCompany } from './useCreateCompany'
import { useDeleteCompany } from './useDeleteCompany'
import { useUpdateCompany } from './useUpdateCompany'
import type { CompanyUpdate } from './types'

interface Props {
  /** Navega al panel de facturas (S3.1) filtrado por esta empresa. Sin app-shell aún: el llamante
   * decide cómo mostrarlo; sin esta prop, el botón "Ver facturas" queda inerte. */
  onViewInvoices?: (companyId: string) => void
}

const EMPTY_FORM = { name: '', cif: '', notes: '' }

export function CompaniesPanel({ onViewInvoices }: Props) {
  const companies = useCompaniesPanel()
  const createCompany = useCreateCompany()
  const updateCompany = useUpdateCompany()
  const deleteCompany = useDeleteCompany()
  const [form, setForm] = useState(EMPTY_FORM)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const rows = companies.data ?? []

  const handleCreate = (e: FormEvent) => {
    e.preventDefault()
    createCompany.mutate(
      { name: form.name, cif: form.cif, notes: form.notes === '' ? null : form.notes },
      { onSuccess: () => setForm(EMPTY_FORM) },
    )
  }

  const handleDelete = (companyId: string) => {
    setDeletingId(companyId)
    // No se limpia `deletingId` en error: la fila debe seguir mostrando su mensaje (p. ej.
    // `CompanyHasMembers`, 409) hasta el siguiente intento. Al borrar con éxito la fila desaparece
    // de la lista (se invalida la query), así que no hace falta limpiarlo explícitamente tampoco.
    deleteCompany.mutate(companyId)
  }

  const handleSave = (companyId: string, body: CompanyUpdate) => {
    updateCompany.mutate({ companyId, body })
  }

  return (
    <section className="mx-auto max-w-5xl space-y-8 p-6 text-slate-100">
      <div>
        <h1 className="text-xl font-semibold">Empresas</h1>

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
            CIF
            <input
              required
              value={form.cif}
              onChange={(e) => setForm((f) => ({ ...f, cif: e.target.value }))}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
            />
          </label>
          <label className="flex flex-col text-sm text-slate-300">
            Notas
            <input
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
              className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
            />
          </label>
          <button
            type="submit"
            disabled={createCompany.isPending}
            className="rounded-md border border-slate-600 px-4 py-2 text-slate-100 disabled:opacity-40"
          >
            {createCompany.isPending ? 'Creando…' : 'Nueva empresa'}
          </button>
        </form>
        {createCompany.isError && (
          <p role="alert" className="mt-2 text-sm text-red-400">
            {createCompany.error instanceof Error
              ? createCompany.error.message
              : 'No se pudo crear la empresa.'}
          </p>
        )}
      </div>

      {companies.isLoading && <p className="text-slate-400">Cargando…</p>}

      {companies.isError && (
        <p role="alert" className="text-red-400">
          No se pudieron cargar las empresas. Inténtalo de nuevo.
        </p>
      )}

      {!companies.isLoading && !companies.isError && rows.length === 0 && (
        <p className="text-slate-400">Todavía no hay empresas.</p>
      )}

      {!companies.isLoading && !companies.isError && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm" data-testid="companies-table">
            <thead className="text-slate-400">
              <tr>
                <th className="p-2">Nombre</th>
                <th className="p-2">CIF</th>
                <th className="p-2">Estado</th>
                <th className="p-2">Notas</th>
                <th className="p-2">Usuarios</th>
                <th className="p-2">Facturas</th>
                <th className="p-2">Última factura</th>
                <th className="p-2">Alta</th>
                <th className="p-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {rows.map((company) => (
                <CompanyTableRow
                  key={company.id}
                  company={company}
                  onSave={(body) => handleSave(company.id, body)}
                  onDelete={() => handleDelete(company.id)}
                  onViewInvoices={() => onViewInvoices?.(company.id)}
                  saving={updateCompany.isPending && updateCompany.variables?.companyId === company.id}
                  deleteError={
                    deleteCompany.isError && deletingId === company.id
                      ? deleteCompany.error instanceof Error
                        ? deleteCompany.error.message
                        : 'No se pudo borrar la empresa.'
                      : null
                  }
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <PendingRegistrations />
      <PurgeTestInvoices />
    </section>
  )
}

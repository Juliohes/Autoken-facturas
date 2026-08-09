// Pantalla "Empresas" de la asesoría (S3.4): ficha agregada (contadores) + alta (reutiliza el CRUD
// de S1.5 tal cual) + registros pendientes (reutiliza S1.4 tal cual). Solo `tenant_admin`/
// admin-tech la ve (portero de roles en el backend; aquí no se repite esa comprobación).
//
// Rediseño 2026-08-09 (a petición de Julio, tras usar el panel): la fila de cada empresa se
// achica al máximo (solo "Ver facturas"). "Editar" y "Borrar" pasan de ser botones por fila a un
// único control junto a "Nueva empresa": "Editar" activa la edición de CUALQUIER celda de
// CUALQUIER fila a la vez (mismo patrón ya usado en `InvoicesPanel`); "Borrar" activa un modo de
// selección (columna de casillas, solo visible en ese modo) con borrado múltiple tras un aviso
// emergente de confirmación. El historial de ediciones se retira del todo por ahora (decisión de
// Julio). Las columnas se pueden arrastrar para cambiar su ancho, estilo Excel, recordado en este
// navegador (`useResizableColumns`).
import { useState, type FormEvent } from 'react'

import { ResizableTh } from '../../shared/ResizableTh'
import { ScrollableTable } from '../../shared/ScrollableTable'
import { useResizableColumns } from '../../shared/useResizableColumns'
import { CompanyTableRow } from './CompanyTableRow'
import { ConfirmDeleteCompaniesDialog } from './ConfirmDeleteCompaniesDialog'
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

// Notas muy estrecha por defecto (a petición explícita de Julio); el resto, ajustado para caber
// sin desperdiciar ancho en la mayoría de pantallas — todas arrastrables desde ahí en adelante.
const DEFAULT_COLUMN_WIDTHS = {
  name: 160,
  cif: 110,
  status: 90,
  notes: 70,
  users: 70,
  invoices: 70,
  lastInvoice: 100,
  createdAt: 100,
}

export function CompaniesPanel({ onViewInvoices }: Props) {
  const companies = useCompaniesPanel()
  const createCompany = useCreateCompany()
  const updateCompany = useUpdateCompany()
  const deleteCompany = useDeleteCompany()
  const { widths, startResize } = useResizableColumns(
    'companies-panel-column-widths',
    DEFAULT_COLUMN_WIDTHS,
  )
  const [form, setForm] = useState(EMPTY_FORM)
  const [editing, setEditing] = useState(false)
  const [deleteMode, setDeleteMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [bulkError, setBulkError] = useState<string | null>(null)

  const rows = companies.data ?? []

  const handleCreate = (e: FormEvent) => {
    e.preventDefault()
    createCompany.mutate(
      { name: form.name, cif: form.cif, notes: form.notes === '' ? null : form.notes },
      { onSuccess: () => setForm(EMPTY_FORM) },
    )
  }

  const handleSave = (companyId: string, body: CompanyUpdate) => {
    updateCompany.mutate({ companyId, body })
  }

  const toggleEditing = () => {
    setEditing((prev) => !prev)
    setDeleteMode(false)
  }

  const cancelDeleteMode = () => {
    setDeleteMode(false)
    setSelectedIds(new Set())
    setBulkError(null)
  }

  const toggleDeleteMode = () => {
    if (deleteMode) {
      cancelDeleteMode()
    } else {
      setDeleteMode(true)
      setEditing(false)
    }
  }

  const toggleSelected = (companyId: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(companyId)) next.delete(companyId)
      else next.add(companyId)
      return next
    })

  const selectedCompanies = rows.filter((row) => selectedIds.has(row.id))

  const confirmBulkDelete = async () => {
    setBulkDeleting(true)
    setBulkError(null)
    const results = await Promise.allSettled(
      selectedCompanies.map((row) => deleteCompany.mutateAsync(row.id)),
    )
    const failedNames = selectedCompanies
      .filter((_, i) => results[i]?.status === 'rejected')
      .map((row) => row.name)
    setBulkDeleting(false)
    if (failedNames.length > 0) {
      setBulkError(`No se pudieron borrar: ${failedNames.join(', ')}.`)
      setConfirmOpen(false)
    } else {
      setConfirmOpen(false)
      cancelDeleteMode()
    }
  }

  return (
    <section className="mx-auto max-w-5xl space-y-8 p-6 text-slate-100">
      <div>
        <h1 className="text-xl font-semibold">Empresas</h1>

        <div className="mt-3 flex flex-wrap items-end justify-between gap-3">
          <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
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

          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={toggleEditing}
              disabled={deleteMode}
              className="rounded-md border border-slate-600 px-4 py-2 text-slate-100 disabled:opacity-40"
            >
              {editing ? 'Terminar edición' : 'Editar'}
            </button>
            <button
              type="button"
              onClick={toggleDeleteMode}
              disabled={editing}
              className="rounded-md border border-slate-600 px-4 py-2 text-slate-100 disabled:opacity-40"
            >
              {deleteMode ? 'Cancelar' : 'Borrar'}
            </button>
            {deleteMode && (
              <button
                type="button"
                onClick={() => setConfirmOpen(true)}
                disabled={selectedIds.size === 0}
                className="rounded-md border border-red-500 px-4 py-2 text-red-400 disabled:opacity-40"
              >
                Borrar seleccionadas ({selectedIds.size})
              </button>
            )}
          </div>
        </div>

        {createCompany.isError && (
          <p role="alert" className="mt-2 text-sm text-red-400">
            {createCompany.error instanceof Error
              ? createCompany.error.message
              : 'No se pudo crear la empresa.'}
          </p>
        )}
        {bulkError && (
          <p role="alert" className="mt-2 text-sm text-red-400">
            {bulkError}
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
        <ScrollableTable>
          <table
            className="whitespace-nowrap text-left text-sm"
            style={{ tableLayout: 'fixed' }}
            data-testid="companies-table"
          >
            <thead className="text-slate-400">
              <tr>
                {deleteMode && <th className="p-2" style={{ width: 32 }} />}
                <ResizableTh label="Nombre" width={widths.name} onResizeStart={startResize('name')} />
                <ResizableTh label="CIF" width={widths.cif} onResizeStart={startResize('cif')} />
                <ResizableTh
                  label="Estado"
                  width={widths.status}
                  onResizeStart={startResize('status')}
                />
                <ResizableTh
                  label="Notas"
                  width={widths.notes}
                  onResizeStart={startResize('notes')}
                />
                <ResizableTh
                  label="Usuarios"
                  width={widths.users}
                  onResizeStart={startResize('users')}
                />
                <ResizableTh
                  label="Facturas"
                  width={widths.invoices}
                  onResizeStart={startResize('invoices')}
                />
                <ResizableTh
                  label="Última factura"
                  width={widths.lastInvoice}
                  onResizeStart={startResize('lastInvoice')}
                />
                <ResizableTh
                  label="Alta"
                  width={widths.createdAt}
                  onResizeStart={startResize('createdAt')}
                />
                <th className="p-2" style={{ width: 96 }} />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700">
              {rows.map((company) => (
                <CompanyTableRow
                  key={company.id}
                  company={company}
                  editing={editing}
                  deleteMode={deleteMode}
                  selected={selectedIds.has(company.id)}
                  onToggleSelected={() => toggleSelected(company.id)}
                  onSave={(body) => handleSave(company.id, body)}
                  onViewInvoices={() => onViewInvoices?.(company.id)}
                  saving={updateCompany.isPending && updateCompany.variables?.companyId === company.id}
                />
              ))}
            </tbody>
          </table>
        </ScrollableTable>
      )}

      {confirmOpen && (
        <ConfirmDeleteCompaniesDialog
          names={selectedCompanies.map((row) => row.name)}
          deleting={bulkDeleting}
          onConfirm={confirmBulkDelete}
          onCancel={() => setConfirmOpen(false)}
        />
      )}

      <PendingRegistrations />
      <PurgeTestInvoices />
    </section>
  )
}

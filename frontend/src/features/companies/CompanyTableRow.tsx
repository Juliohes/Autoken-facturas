// Una fila de la tabla de empresas (S3.4): modo lectura o edición inline. Componente propio
// (no vive dentro de `CompaniesPanel`) para no mezclar la orquestación de datos de la pantalla
// con el estado local de edición de una fila.
import { useState } from 'react'

import type { CompanyRow, CompanyUpdate } from './types'

const STATUS_OPTIONS = [
  { value: 'active', label: 'Activa' },
  { value: 'pending', label: 'Pendiente' },
]

interface Props {
  company: CompanyRow
  onSave: (body: CompanyUpdate) => void
  onDelete: () => void
  onViewInvoices: () => void
  saving: boolean
  deleting: boolean
  deleteError: string | null
}

export function CompanyTableRow({
  company,
  onSave,
  onDelete,
  onViewInvoices,
  saving,
  deleting,
  deleteError,
}: Props) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState({
    name: company.name,
    cif: company.cif,
    notes: company.notes ?? '',
    status: company.status,
  })

  const startEditing = () => {
    setDraft({
      name: company.name,
      cif: company.cif,
      notes: company.notes ?? '',
      status: company.status,
    })
    setEditing(true)
  }

  const save = () => {
    onSave({
      name: draft.name,
      cif: draft.cif,
      notes: draft.notes === '' ? null : draft.notes,
      status: draft.status as 'active' | 'pending',
    })
    setEditing(false)
  }

  if (editing) {
    return (
      <tr data-testid="company-row" data-editing="true">
        <td className="p-2">
          <input
            aria-label="Nombre"
            value={draft.name}
            onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </td>
        <td className="p-2">
          <input
            aria-label="CIF"
            value={draft.cif}
            onChange={(e) => setDraft((d) => ({ ...d, cif: e.target.value }))}
            className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </td>
        <td className="p-2">
          <select
            aria-label="Estado"
            value={draft.status}
            onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))}
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </td>
        <td className="p-2">
          <input
            aria-label="Notas"
            value={draft.notes}
            onChange={(e) => setDraft((d) => ({ ...d, notes: e.target.value }))}
            className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1"
          />
        </td>
        <td className="p-2">{company.user_count}</td>
        <td className="p-2">{company.invoice_count}</td>
        <td className="p-2">{company.last_invoice_at ?? '—'}</td>
        <td className="p-2">{company.created_at}</td>
        <td className="p-2 space-x-2">
          <button
            type="button"
            onClick={save}
            disabled={saving}
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
        </td>
      </tr>
    )
  }

  return (
    <tr data-testid="company-row">
      <td className="p-2">{company.name}</td>
      <td className="p-2">{company.cif}</td>
      <td className="p-2">{company.status === 'active' ? 'Activa' : 'Pendiente'}</td>
      <td className="p-2">{company.notes ?? '—'}</td>
      <td className="p-2">{company.user_count}</td>
      <td className="p-2">{company.invoice_count}</td>
      <td className="p-2">{company.last_invoice_at ?? '—'}</td>
      <td className="p-2">{company.created_at}</td>
      <td className="p-2 space-x-2">
        <button type="button" onClick={startEditing} className="text-emerald-400 underline">
          Editar
        </button>
        <button type="button" onClick={onViewInvoices} className="text-emerald-400 underline">
          Ver facturas
        </button>
        <button
          type="button"
          onClick={onDelete}
          disabled={deleting}
          className="text-red-400 underline disabled:opacity-40"
        >
          {deleting ? 'Borrando…' : 'Borrar'}
        </button>
        {deleteError && (
          <p role="alert" className="text-xs text-red-400">
            {deleteError}
          </p>
        )}
      </td>
    </tr>
  )
}

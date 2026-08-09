// Una fila de la tabla de empresas (S3.4; rediseño 2026-08-09 a petición de Julio: la fila deja de
// tener botones propios —salvo "Ver facturas"— para quedar lo más estrecha posible. La edición y
// el borrado pasan a ser globales, gobernados por `CompaniesPanel` (un único "Editar"/"Borrar"
// junto a "Nueva empresa", no un botón por fila): esta fila solo sabe presentarse en modo lectura,
// modo edición (`editing`) o modo selección para borrar (`deleteMode`), según le digan desde fuera.
import { formatDate } from '../../shared/format'
import type { CompanyRow, CompanyUpdate } from './types'

const STATUS_OPTIONS = [
  { value: 'active', label: 'Activa' },
  { value: 'pending', label: 'Pendiente' },
]

interface EditableCellProps {
  companyId: string
  field: 'name' | 'cif' | 'notes'
  value: string | null
  label: string
  saving: boolean
  onSave: (body: CompanyUpdate) => void
}

/** Una celda editable individual: se guarda sola al perder el foco, si el valor cambió de verdad
 * (mismo patrón ya establecido en `InvoicesPanel`, "un único botón activa la edición de cualquier
 * celda de cualquier fila"). */
function EditableCell({ companyId, field, value, label, saving, onSave }: EditableCellProps) {
  const current = value ?? ''
  return (
    <input
      key={`${companyId}-${field}-${current}`}
      type="text"
      aria-label={label}
      defaultValue={current}
      disabled={saving}
      onBlur={(e) => {
        const next = e.target.value
        if (next === current) return
        onSave({ [field]: field === 'notes' && next === '' ? null : next } as CompanyUpdate)
      }}
      className="w-full rounded border border-slate-600 bg-slate-800 px-2 py-1 disabled:opacity-40"
    />
  )
}

interface Props {
  company: CompanyRow
  editing: boolean
  deleteMode: boolean
  selected: boolean
  onToggleSelected: () => void
  onSave: (body: CompanyUpdate) => void
  onViewInvoices: () => void
  saving: boolean
}

export function CompanyTableRow({
  company,
  editing,
  deleteMode,
  selected,
  onToggleSelected,
  onSave,
  onViewInvoices,
  saving,
}: Props) {
  return (
    <tr data-testid="company-row">
      {deleteMode && (
        <td className="p-2">
          <input
            type="checkbox"
            aria-label={`Seleccionar ${company.name}`}
            checked={selected}
            onChange={onToggleSelected}
          />
        </td>
      )}
      <td className="p-2">
        {editing ? (
          <EditableCell
            companyId={company.id}
            field="name"
            value={company.name}
            label="Nombre"
            saving={saving}
            onSave={onSave}
          />
        ) : (
          company.name
        )}
      </td>
      <td className="p-2">
        {editing ? (
          <EditableCell
            companyId={company.id}
            field="cif"
            value={company.cif}
            label="CIF"
            saving={saving}
            onSave={onSave}
          />
        ) : (
          company.cif
        )}
      </td>
      <td className="p-2">
        {editing ? (
          <select
            aria-label="Estado"
            defaultValue={company.status}
            disabled={saving}
            onChange={(e) => onSave({ status: e.target.value as 'active' | 'pending' })}
            className="rounded border border-slate-600 bg-slate-800 px-2 py-1 disabled:opacity-40"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        ) : company.status === 'active' ? (
          'Activa'
        ) : (
          'Pendiente'
        )}
      </td>
      <td className="p-2">
        {editing ? (
          <EditableCell
            companyId={company.id}
            field="notes"
            value={company.notes}
            label="Notas"
            saving={saving}
            onSave={onSave}
          />
        ) : (
          (company.notes ?? '—')
        )}
      </td>
      <td className="p-2">{company.user_count}</td>
      <td className="p-2">{company.invoice_count}</td>
      <td className="p-2">{formatDate(company.last_invoice_at)}</td>
      <td className="p-2">{formatDate(company.created_at)}</td>
      <td className="p-2">
        <button type="button" onClick={onViewInvoices} className="text-emerald-400 underline">
          Ver facturas
        </button>
      </td>
    </tr>
  )
}

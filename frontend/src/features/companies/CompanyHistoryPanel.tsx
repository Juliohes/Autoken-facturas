// Historial de ediciones de una empresa (2026-08-01, decisión de Julio): componente propio,
// extraído de `CompanyTableRow` para no mezclar la orquestación de la fila con la carga/estado del
// historial (mismo criterio que `TenantRowActions`).
import { formatDateTime } from '../../shared/format'
import { useCompanyHistory } from './useCompanyHistory'
import type { CompanyUpdate } from './types'

const FIELD_LABEL: Record<string, string> = {
  name: 'Nombre',
  cif: 'CIF',
  notes: 'Notas',
  status: 'Estado',
}

/** Construye el patch de "revertir a este valor" para el campo de una entrada del historial. Solo
 * `status` necesita un valor literal ('active'|'pending'); el resto es texto libre tal cual. */
function revertBody(field: string, value: string | null): CompanyUpdate | null {
  switch (field) {
    case 'name':
      return { name: value ?? '' }
    case 'cif':
      return { cif: value ?? '' }
    case 'notes':
      return { notes: value }
    case 'status':
      return value === 'active' || value === 'pending' ? { status: value } : null
    default:
      return null
  }
}

interface Props {
  companyId: string
  onRevert: (body: CompanyUpdate) => void
  saving: boolean
}

export function CompanyHistoryPanel({ companyId, onRevert, saving }: Props) {
  const history = useCompanyHistory(companyId, true)

  if (history.isLoading) return <p className="p-2 text-slate-400">Cargando historial…</p>

  if (history.isError) {
    return (
      <p role="alert" className="p-2 text-red-400">
        No se pudo cargar el historial. Inténtalo de nuevo.
      </p>
    )
  }

  const entries = history.data ?? []

  if (entries.length === 0) {
    return <p className="p-2 text-slate-400">Todavía no hay ediciones registradas.</p>
  }

  return (
    <ul className="divide-y divide-slate-700" data-testid="company-history-list">
      {entries.map((entry) => {
        const body = revertBody(entry.field, entry.old_value)
        return (
          <li
            key={entry.id}
            data-testid="company-history-row"
            className="flex flex-wrap items-center justify-between gap-2 p-2 text-sm"
          >
            <span>
              <span className="font-medium">{FIELD_LABEL[entry.field] ?? entry.field}</span>:{' '}
              <span className="text-slate-400">{entry.old_value ?? '—'}</span>
              {' → '}
              <span>{entry.new_value ?? '—'}</span>
              <span className="ml-2 text-xs text-slate-500">
                {formatDateTime(entry.edited_at, { seconds: true })}
              </span>
            </span>
            {body && (
              <button
                type="button"
                onClick={() => onRevert(body)}
                disabled={saving}
                className="text-xs text-emerald-400 underline disabled:opacity-40"
              >
                Revertir a este valor
              </button>
            )}
          </li>
        )
      })}
    </ul>
  )
}

// Historial de ediciones de una factura (2026-08-01, decisión de Julio): mismo patrón que
// `CompanyHistoryPanel` (empresas).
import { formatCurrency, formatDateTime } from '../../shared/format'
import { useInvoiceHistory } from './useInvoiceHistory'
import type { InvoiceEditIn } from './types'

const FIELD_LABEL: Record<string, string> = {
  issue_date: 'Fecha',
  counterparty_tax_id: 'CIF',
  counterparty_name: 'Proveedor',
  net_amount: 'Base',
  tax_amount: 'IVA',
  total_amount: 'Total',
  irpf_amount: 'IRPF',
}

const CURRENCY_FIELDS = new Set(['net_amount', 'tax_amount', 'total_amount', 'irpf_amount'])

/** Igual que en el resto de la app: los importes siempre con coma decimal, nunca en crudo. */
function displayValue(field: string, value: string | null): string {
  return CURRENCY_FIELDS.has(field) ? formatCurrency(value) : (value ?? '—')
}

/** Construye el patch de "revertir a este valor" para el campo de una entrada del historial.
 * `null` para campos que esta pantalla no edita (p. ej. tramos de IVA sueltos, `tax_line[21].base`)
 * — la entrada se sigue mostrando, solo sin botón de revertir. */
function revertBody(field: string, value: string | null): InvoiceEditIn | null {
  switch (field) {
    case 'issue_date':
      return { issue_date: value }
    case 'counterparty_tax_id':
      return { counterparty_tax_id: value }
    case 'counterparty_name':
      return { counterparty_name: value }
    case 'net_amount':
      return { net_amount: value }
    case 'tax_amount':
      return { tax_amount: value }
    case 'total_amount':
      return { total_amount: value }
    case 'irpf_amount':
      return { irpf_amount: value }
    default:
      return null
  }
}

interface Props {
  invoiceId: string
  onRevert: (body: InvoiceEditIn) => void
  saving: boolean
}

export function InvoiceHistoryPanel({ invoiceId, onRevert, saving }: Props) {
  const history = useInvoiceHistory(invoiceId, true)

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
    <ul className="divide-y divide-slate-700" data-testid="invoice-history-list">
      {entries.map((entry) => {
        const body = revertBody(entry.field, entry.old_value)
        return (
          <li
            key={entry.id}
            data-testid="invoice-history-row"
            className="flex flex-wrap items-center justify-between gap-2 p-2 text-sm"
          >
            <span>
              <span className="font-medium">{FIELD_LABEL[entry.field] ?? entry.field}</span>:{' '}
              <span className="text-slate-400">{displayValue(entry.field, entry.old_value)}</span>
              {' → '}
              <span>{displayValue(entry.field, entry.new_value)}</span>
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

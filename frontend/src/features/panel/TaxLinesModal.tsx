// Ventana de tramos de IVA de una factura (2026-08-01, decisión de Julio: "un botón indicando el
// número de tramos, y al darle una ventana pequeña desglosando cada parte de IVA, editable").
// `PATCH /invoices/{id}` reemplaza el conjunto COMPLETO de tramos (S3.3): se guarda todo junto, no
// tramo a tramo — de ahí que este modal tenga su propio "Guardar", a diferencia de las demás
// celdas del panel (que se guardan solas al perder el foco).
import { useState } from 'react'

import { fromAmountInputValue, toAmountInputValue } from '../../shared/format'
import { Modal } from '../../shared/Modal'
import { useEditInvoice } from './useEditInvoice'
import type { InvoiceRow } from './types'

interface TaxLineDraft {
  iva_pct: string
  base: string
  cuota: string
}

// `base`/`cuota` con coma decimal (2026-08-08, hallazgo de Julio: esta ventana seguía mostrando
// el punto crudo del backend); `iva_pct` es un tipo (%), no un importe, se deja tal cual.
function draftsFrom(row: InvoiceRow): TaxLineDraft[] {
  if (row.tax_lines.length === 0) return [{ iva_pct: '', base: '', cuota: '' }]
  return row.tax_lines.map((line) => ({
    iva_pct: line.iva_pct ?? '',
    base: toAmountInputValue(line.base),
    cuota: toAmountInputValue(line.cuota),
  }))
}

interface Props {
  invoice: InvoiceRow
  onClose: () => void
}

export function TaxLinesModal({ invoice, onClose }: Props) {
  const editInvoice = useEditInvoice()
  const [lines, setLines] = useState<TaxLineDraft[]>(draftsFrom(invoice))

  const updateLine = (index: number, patch: Partial<TaxLineDraft>) =>
    setLines((prev) => prev.map((line, i) => (i === index ? { ...line, ...patch } : line)))

  const addLine = () => setLines((prev) => [...prev, { iva_pct: '', base: '', cuota: '' }])
  const removeLine = (index: number) => setLines((prev) => prev.filter((_, i) => i !== index))

  const save = () => {
    const tax_lines = lines
      .filter((line) => line.iva_pct !== '' || line.base !== '' || line.cuota !== '')
      .map((line) => ({
        iva_pct: line.iva_pct === '' ? null : line.iva_pct,
        base: fromAmountInputValue(line.base),
        cuota: fromAmountInputValue(line.cuota),
      }))
    editInvoice.mutate({ invoiceId: invoice.id, body: { tax_lines } }, { onSuccess: onClose })
  }

  return (
    <Modal title="Tramos de IVA" onClose={onClose} panelClassName="max-w-lg space-y-3">
        <div className="space-y-2">
          {lines.map((line, i) => (
            <div key={i} className="flex flex-wrap items-end gap-2">
              <label className="flex flex-col text-xs text-slate-300">
                % IVA
                <input
                  aria-label={`Tramo ${i + 1}: % IVA`}
                  value={line.iva_pct}
                  onChange={(e) => updateLine(i, { iva_pct: e.target.value })}
                  className="w-16 rounded border border-slate-600 bg-slate-900 px-2 py-1"
                />
              </label>
              <label className="flex flex-col text-xs text-slate-300">
                Base
                <input
                  aria-label={`Tramo ${i + 1}: Base`}
                  value={line.base}
                  onChange={(e) => updateLine(i, { base: e.target.value })}
                  className="w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1"
                />
              </label>
              <label className="flex flex-col text-xs text-slate-300">
                Cuota
                <input
                  aria-label={`Tramo ${i + 1}: Cuota`}
                  value={line.cuota}
                  onChange={(e) => updateLine(i, { cuota: e.target.value })}
                  className="w-24 rounded border border-slate-600 bg-slate-900 px-2 py-1"
                />
              </label>
              <button
                type="button"
                onClick={() => removeLine(i)}
                className="text-xs text-red-400 underline"
              >
                Quitar
              </button>
            </div>
          ))}
        </div>

        <button type="button" onClick={addLine} className="text-xs text-emerald-400 underline">
          + Añadir tramo
        </button>

        {editInvoice.isError && (
          <p role="alert" className="text-xs text-red-400">
            {editInvoice.error instanceof Error
              ? editInvoice.error.message
              : 'No se pudieron guardar los tramos.'}
          </p>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-600 px-3 py-1 text-sm"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={save}
            disabled={editInvoice.isPending}
            className="rounded bg-emerald-600 px-3 py-1 text-sm font-medium text-white disabled:opacity-40"
          >
            {editInvoice.isPending ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
    </Modal>
  )
}

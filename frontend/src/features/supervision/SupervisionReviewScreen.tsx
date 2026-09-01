import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'

import { ROUTES } from '../../app/routes'
import { api } from '../../api/client'
import type { ReviewResponse } from '../confirmation/types'

export function SupervisionReviewScreen({ fileId }: { fileId: string }) {
  const review = useQuery({
    queryKey: ['supervision-review', fileId],
    queryFn: async (): Promise<ReviewResponse> => {
      const { data, error } = await api.GET('/api/v1/uploads/{file_id}/review-readonly', {
        params: { path: { file_id: fileId } },
      })
      if (error || !data) throw new Error('No se pudo abrir el pendiente')
      return data as unknown as ReviewResponse
    },
  })

  if (review.isLoading) return <p className="p-6 text-slate-400">Cargando revisión...</p>
  if (review.isError || !review.data) {
    return <p role="alert" className="p-6 text-red-400">No se pudo abrir este pendiente.</p>
  }

  return (
      <section className="tn-panel-page mx-auto max-w-2xl space-y-5 p-6">
      <Link to={ROUTES.supervision} className="text-sm text-emerald-400">Volver a pendientes</Link>
      <div>
        <h1 className="text-xl font-semibold">Revisión de supervisión</h1>
        <p className="mt-1 text-sm text-slate-400">Solo lectura. El borrador pertenece a quien subió el documento.</p>
      </div>
      <dl className="space-y-2 rounded-md border border-slate-700 p-4">
        {Object.entries(review.data.fields).map(([name, value]) => (
          <div key={name} className="flex justify-between gap-4 border-b border-slate-800 py-2 last:border-0">
            <dt className="text-sm text-slate-400">{FIELD_LABEL[name] ?? name}</dt>
            <dd className="text-right text-sm text-slate-100">{formatValue(value)}</dd>
          </div>
        ))}
      </dl>
      <p className="text-sm text-slate-400">Origen: {review.data.source === 'draft' ? 'borrador' : 'OCR'}</p>
    </section>
  )
}

const FIELD_LABEL: Record<string, string> = {
  issue_date: 'Fecha',
  invoice_number: 'Número de factura',
  counterparty_tax_id: 'CIF de contraparte',
  counterparty_name: 'Contraparte',
  net_amount: 'Base imponible',
  tax_amount: 'IVA',
  total_amount: 'Total',
  irpf_amount: 'IRPF',
  tax_lines: 'Tramos de IVA',
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '-'
  return typeof value === 'string' ? value : JSON.stringify(value)
}

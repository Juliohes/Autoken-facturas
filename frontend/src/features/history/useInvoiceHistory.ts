// Hook de datos del historial (S2.6): consulta `GET /invoices/history` con el
// cliente tipado y devuelve la respuesta como `HistoryResponse` de dominio.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { HistoryResponse } from './types'

export function useInvoiceHistory(cursor: string | null = null) {
  return useQuery<HistoryResponse>({
    queryKey: ['invoice-history', cursor],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/invoices/history', { params: { query: { cursor, limit: 20 } } })
      if (error || !data) throw new Error('No se pudo cargar el historial de facturas')
      return data
    },
  })
}

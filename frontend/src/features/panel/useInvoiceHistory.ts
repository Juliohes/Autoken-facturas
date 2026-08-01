// Hook de datos del historial de ediciones de una factura (2026-08-01): `GET
// /invoices/{id}/history`. `enabled`: solo se pide cuando la fila lo tiene abierto.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useInvoiceHistory(invoiceId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['invoice-history', invoiceId],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/invoices/{invoice_id}/history', {
        params: { path: { invoice_id: invoiceId } },
      })
      if (error || !data) throw new Error('No se pudo cargar el historial')
      return data
    },
    enabled,
  })
}

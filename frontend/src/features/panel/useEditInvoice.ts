// Hook de edición de factura (reutiliza `PATCH /invoices/{id}` de S3.3 tal cual, ahora también
// desde el panel, 2026-08-01): patch parcial, solo los campos presentes cambian.
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'
import type { InvoiceEditIn } from './types'

export function useEditInvoice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ invoiceId, body }: { invoiceId: string; body: InvoiceEditIn }) => {
      const { data, error } = await api.PATCH('/api/v1/invoices/{invoice_id}', {
        params: { path: { invoice_id: invoiceId } },
        body,
      })
      if (error) throw new Error(errorDetail(error) ?? 'No se pudo editar la factura')
      return data
    },
    onSuccess: (_data, { invoiceId }) => {
      queryClient.invalidateQueries({ queryKey: ['invoices-panel'] })
      // Igual que en empresas: un `Revertir` del historial es una edición más, así que si el
      // historial de esta factura está abierto debe reflejarla al instante.
      queryClient.invalidateQueries({ queryKey: ['invoice-history', invoiceId] })
    },
  })
}

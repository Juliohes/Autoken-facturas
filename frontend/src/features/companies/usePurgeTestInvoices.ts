// Hook de la purga de facturas de prueba (S3.5): `POST /invoices/test/purge`, borra de una vez
// todas las visibles en el contexto del tenant_admin. Sin parámetros: el servidor decide qué borra
// (spec S3.5 regla de dominio 2), este hook no puede pedir un subconjunto.
import { useMutation } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from './errors'

export function usePurgeTestInvoices() {
  return useMutation({
    mutationFn: async () => {
      const { data, error } = await api.POST('/api/v1/invoices/test/purge')
      if (error || !data) throw new Error(errorDetail(error) ?? 'No se pudo purgar')
      return data.purged
    },
  })
}

// Hook de datos del detalle del laboratorio OCR (S6.2, spec C6-C13): `GET
// /platform/tenants/{tenant_id}/invoices/{file_id}/lab`. Deshabilitado hasta que se elige una
// factura concreta (se abre bajo demanda al pulsar "Laboratorio" en una fila).
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { LabDetail } from './labTypes'

export function useInvoiceLab(tenantId: string | null, fileId: string | null) {
  return useQuery<LabDetail>({
    queryKey: ['platform-lab-detail', tenantId, fileId],
    enabled: tenantId !== null && fileId !== null,
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/api/v1/platform/tenants/{tenant_id}/invoices/{file_id}/lab',
        { params: { path: { tenant_id: tenantId as string, file_id: fileId as string } } },
      )
      if (error || !data) throw new Error('No se pudo cargar el laboratorio de esta factura')
      return data as unknown as LabDetail
    },
  })
}

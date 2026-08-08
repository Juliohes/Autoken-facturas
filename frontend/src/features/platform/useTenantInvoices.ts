// Hook de datos del listado de facturas confirmadas de UN tenant, desde el laboratorio OCR (S6.2,
// spec C2): `GET /platform/tenants/{tenant_id}/invoices`. Deshabilitado hasta que se elige un
// tenant (mismo criterio que `useOcrRanking`: evita un GET sin sentido con `tenant_id` vacío).
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { LabInvoiceRow } from './labTypes'

export function useTenantInvoices(tenantId: string | null) {
  return useQuery<LabInvoiceRow[]>({
    queryKey: ['platform-lab-invoices', tenantId],
    enabled: tenantId !== null,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/tenants/{tenant_id}/invoices', {
        params: { path: { tenant_id: tenantId as string } },
      })
      if (error || !data) throw new Error('No se pudieron cargar las facturas de este tenant')
      return data
    },
  })
}

// Hook de datos de métricas y consumo (S4.5): consulta `GET /platform/tenants/metrics` (solo
// lectura, sin filtros, mismo criterio que `useTenants`).
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useTenantMetrics() {
  return useQuery({
    queryKey: ['platform-tenant-metrics'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/tenants/metrics')
      if (error || !data) throw new Error('No se pudieron cargar las métricas')
      return data
    },
  })
}

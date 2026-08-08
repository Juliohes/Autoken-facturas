// Hook de datos del listado de tenants (S4.1): consulta `GET /platform/tenants` (solo lectura,
// sin filtros ni paginación, spec §0 decisión 7).
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

// `enabled` (S6.2, laboratorio): permite que una pantalla solo admin-tech evite el GET cuando el
// usuario no tiene el flag (mismo criterio que `useOcrRanking`), sin afectar a `PlatformTenants`
// (siempre `true` por defecto, no toca su comportamiento).
export function useTenants(enabled = true) {
  return useQuery({
    queryKey: ['platform-tenants'],
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/tenants')
      if (error || !data) throw new Error('No se pudieron cargar los tenants')
      return data
    },
  })
}

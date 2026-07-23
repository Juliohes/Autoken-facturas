// Hook de datos del listado de tenants (S4.1): consulta `GET /platform/tenants` (solo lectura,
// sin filtros ni paginación, spec §0 decisión 7).
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useTenants() {
  return useQuery({
    queryKey: ['platform-tenants'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/tenants')
      if (error || !data) throw new Error('No se pudieron cargar los tenants')
      return data
    },
  })
}

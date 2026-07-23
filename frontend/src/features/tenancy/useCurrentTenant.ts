// Hook de datos del tenant actual (S1.2/S4.2): consulta `GET /tenants/current` (público, sin
// auth). 404 en hosts sin tenant (plataforma, subdominio inexistente) es un caso normal, no un
// error a mostrar: lo traduce `useTenantTheme` a los valores por defecto.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useCurrentTenant() {
  return useQuery({
    queryKey: ['current-tenant'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/tenants/current')
      if (error || !data) throw new Error('No hay tenant resuelto para este host')
      return data
    },
    retry: false,
  })
}

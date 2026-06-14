import { useQuery } from '@tanstack/react-query'

import { api } from './client'

// Hook que consulta el healthcheck del backend usando el cliente tipado.
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/health')
      if (error) throw new Error('Healthcheck falló')
      return data
    },
  })
}

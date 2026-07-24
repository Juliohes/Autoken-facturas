// Hook de lectura del interruptor admin-tech (S4.10): `GET /platform/settings`.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useAdminSettings() {
  return useQuery({
    queryKey: ['platform-settings'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/settings')
      if (error || !data) throw new Error('No se pudo cargar el ajuste')
      return data
    },
  })
}

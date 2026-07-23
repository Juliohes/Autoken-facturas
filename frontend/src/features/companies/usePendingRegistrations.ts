// Hook de datos de los registros pendientes de aprobación (reutiliza `GET /registrations` de
// S1.4 tal cual).
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function usePendingRegistrations() {
  return useQuery({
    queryKey: ['pending-registrations'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/registrations')
      if (error || !data) throw new Error('No se pudieron cargar los registros pendientes')
      return data
    },
  })
}

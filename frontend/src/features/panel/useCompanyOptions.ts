// Hook de datos de las empresas de la asesoría (para el filtro "empresa" del panel, S3.1).
// Reutiliza el endpoint de S1.5 (`GET /companies`) tal cual, sin duplicar lógica.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useCompanyOptions() {
  return useQuery({
    queryKey: ['companies'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/companies')
      if (error || !data) throw new Error('No se pudieron cargar las empresas')
      return data
    },
  })
}

// Hook de datos de la ficha agregada de empresas (S3.4): consulta
// `GET /reporting/companies` (solo lectura, sin filtros ni paginación).
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useCompaniesPanel() {
  return useQuery({
    queryKey: ['companies-panel'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/reporting/companies')
      if (error || !data) throw new Error('No se pudieron cargar las empresas')
      return data
    },
  })
}

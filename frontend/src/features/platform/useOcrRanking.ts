// Hook de lectura del ranking multi-modelo (S4.8): `GET /platform/ocr-ranking`.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useOcrRanking(enabled: boolean) {
  return useQuery({
    queryKey: ['ocr-ranking'],
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/ocr-ranking')
      if (error || !data) throw new Error('No se pudo cargar el ranking')
      return data
    },
  })
}

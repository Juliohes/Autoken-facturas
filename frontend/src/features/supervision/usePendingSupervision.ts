import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { SupervisionResponse } from './types'

export function usePendingSupervision(cursor: string | null) {
  return useQuery({
    queryKey: ['pending-supervision', cursor],
    queryFn: async (): Promise<SupervisionResponse> => {
      const { data, error } = await api.GET('/api/v1/invoices/pending-supervision', {
        params: { query: { cursor, limit: 20 } },
      })
      if (error || !data) throw new Error('No se pudo cargar la supervisión')
      return data
    },
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  })
}

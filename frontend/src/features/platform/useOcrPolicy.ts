import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useOcrPolicy(enabled: boolean) {
  return useQuery({
    queryKey: ['platform-ocr-policy'],
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/ocr-policy')
      if (error || !data) throw new Error('No se pudo cargar la política OCR')
      return data
    },
  })
}

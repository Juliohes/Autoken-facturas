import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useOcrLabSettings(enabled: boolean) {
  return useQuery({
    queryKey: ['platform-ocr-lab-settings'],
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/ocr-lab/settings')
      if (error || !data) throw new Error('No se pudo cargar la configuración del laboratorio')
      return data
    },
  })
}

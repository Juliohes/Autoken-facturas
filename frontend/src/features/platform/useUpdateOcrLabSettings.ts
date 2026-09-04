import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function useUpdateOcrLabSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: {
      lab_visible: boolean
      auto_benchmark_enabled: boolean
      benchmark_engines: string[]
      benchmark_variants: string[]
    }) => {
      const { data, error } = await api.PUT('/api/v1/platform/ocr-lab/settings', { body })
      if (error || !data) {
        throw new Error(errorDetail(error) ?? 'No se pudo cambiar la configuración del laboratorio')
      }
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform-ocr-lab-settings'] }),
  })
}

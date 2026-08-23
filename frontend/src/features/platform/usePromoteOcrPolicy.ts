import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function usePromoteOcrPolicy() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (policy: {
      version: number
      primary_engine: string
      primary_model: string
      fallback_enabled: boolean
      fallback_engine?: string | null
      fallback_model?: string | null
      consensus_mode: 'primary_only' | 'per_field'
    }) => {
      const { data, error } = await api.POST('/api/v1/platform/ocr-lab/promote', { body: policy })
      if (error || !data) throw new Error(errorDetail(error) ?? 'No se pudo promover la política')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform-ocr-policy'] }),
  })
}

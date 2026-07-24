// Hook de escritura del interruptor admin-tech (S4.10): `PUT /platform/settings`. Sin estado
// optimista (C10): el interruptor de la UI solo refleja lo que el backend ya confirmó, porque
// activarlo dispara gasto real (S2.9/S2.10/S4.8, cuando lean este ajuste).
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function useUpdateAdminSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (ocrExperimentEnabled: boolean) => {
      const { data, error } = await api.PUT('/api/v1/platform/settings', {
        body: { ocr_experiment_enabled: ocrExperimentEnabled },
      })
      if (error || !data) throw new Error(errorDetail(error) ?? 'No se pudo cambiar el ajuste')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform-settings'] }),
  })
}

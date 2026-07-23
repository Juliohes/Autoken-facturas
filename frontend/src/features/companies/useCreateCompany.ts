// Hook de alta de empresa (reutiliza `POST /companies` de S1.5 tal cual).
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'
import type { CompanyCreate } from './types'

export function useCreateCompany() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: CompanyCreate) => {
      const { data, error } = await api.POST('/api/v1/companies', { body })
      if (error) throw new Error(errorDetail(error) ?? 'No se pudo crear la empresa')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['companies-panel'] }),
  })
}

// Hook de edición de empresa (reutiliza `PATCH /companies/{id}` de S1.5 tal cual): nombre, CIF,
// notas y estado, en un patch parcial (solo los campos presentes cambian).
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'
import type { CompanyUpdate } from './types'

export function useUpdateCompany() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ companyId, body }: { companyId: string; body: CompanyUpdate }) => {
      const { data, error } = await api.PATCH('/api/v1/companies/{company_id}', {
        params: { path: { company_id: companyId } },
        body,
      })
      if (error) throw new Error(errorDetail(error) ?? 'No se pudo editar la empresa')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['companies-panel'] }),
  })
}

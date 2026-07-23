// Hook de borrado de empresa (reutiliza `DELETE /companies/{id}` de S1.5 tal cual): 409 si tiene
// usuarios asignados (`CompanyHasMembers`), mensaje que se propaga tal cual al llamante.
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function useDeleteCompany() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (companyId: string) => {
      const { error } = await api.DELETE('/api/v1/companies/{company_id}', {
        params: { path: { company_id: companyId } },
      })
      if (error) throw new Error(errorDetail(error) ?? 'No se pudo borrar la empresa')
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['companies-panel'] }),
  })
}

// Hook de "Reactivar" (S4.7): `POST /platform/tenants/{id}/reactivate`. Revierte `suspend`.
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function useReactivateTenant() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (tenantId: string) => {
      const { data, error } = await api.POST('/api/v1/platform/tenants/{tenant_id}/reactivate', {
        params: { path: { tenant_id: tenantId } },
      })
      if (error || !data) throw new Error(errorDetail(error) ?? 'No se pudo reactivar')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform-tenants'] }),
  })
}

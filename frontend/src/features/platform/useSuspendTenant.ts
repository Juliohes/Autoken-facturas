// Hook de "Suspender" (S4.7): `POST /platform/tenants/{id}/suspend`. Bloquea el login de todos los
// usuarios del tenant sin tocar ningún dato. Invalida el listado, mismo patrón que el resto.
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function useSuspendTenant() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (tenantId: string) => {
      const { data, error } = await api.POST('/api/v1/platform/tenants/{tenant_id}/suspend', {
        params: { path: { tenant_id: tenantId } },
      })
      if (error || !data) throw new Error(errorDetail(error) ?? 'No se pudo suspender')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform-tenants'] }),
  })
}

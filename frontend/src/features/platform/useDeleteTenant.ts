// Hook de "Borrar" (S4.7): `DELETE /platform/tenants/{id}` con `confirm_slug` (segundo factor de
// confirmación verificado en servidor, spec §3 decisión 4). Invalida el listado.
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function useDeleteTenant() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ tenantId, confirmSlug }: { tenantId: string; confirmSlug: string }) => {
      const { error } = await api.DELETE('/api/v1/platform/tenants/{tenant_id}', {
        params: { path: { tenant_id: tenantId } },
        body: { confirm_slug: confirmSlug },
      })
      if (error) throw new Error(errorDetail(error) ?? 'No se pudo borrar el tenant')
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform-tenants'] }),
  })
}

// Hook de "Purgar" un tenant demo (S4.4): `POST /platform/tenants/{id}/purge`. Invalida el listado
// al terminar para que la fila purgada desaparezca sin recargar (mismo patrón que el resto de
// mutaciones de este panel).
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function usePurgeTenant() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (tenantId: string) => {
      const { error } = await api.POST('/api/v1/platform/tenants/{tenant_id}/purge', {
        params: { path: { tenant_id: tenantId } },
      })
      if (error) throw new Error(errorDetail(error) ?? 'No se pudo purgar el tenant')
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform-tenants'] }),
  })
}

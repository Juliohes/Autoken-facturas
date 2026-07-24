// Hook de "Convertir a producción" (S4.4): `POST /platform/tenants/{id}/convert-to-production`.
// Invalida el listado al terminar para que la fila refleje `is_demo: false` sin recargar.
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function useConvertToProduction() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (tenantId: string) => {
      const { data, error } = await api.POST(
        '/api/v1/platform/tenants/{tenant_id}/convert-to-production',
        { params: { path: { tenant_id: tenantId } } },
      )
      if (error || !data) throw new Error(errorDetail(error) ?? 'No se pudo convertir a producción')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform-tenants'] }),
  })
}

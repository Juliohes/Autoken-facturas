// Hook de alta de tenant (S4.1): `POST /platform/tenants`. Invalida el listado al terminar para
// que la nueva fila aparezca sin recargar la pantalla.
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'
import type { TenantCreate } from './types'

export function useCreateTenant() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (body: TenantCreate) => {
      const { data, error } = await api.POST('/api/v1/platform/tenants', { body })
      if (error || !data) throw new Error(errorDetail(error) ?? 'No se pudo crear el tenant')
      return data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['platform-tenants'] }),
  })
}

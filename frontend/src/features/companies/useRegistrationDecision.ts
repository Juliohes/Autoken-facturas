// Hook de decisión sobre un registro pendiente (reutiliza `POST /registrations/{id}/approve|reject`
// de S1.4 tal cual). Una sola mutación parametrizada por `decision`, para no duplicar el mismo
// invalidate/error-handling en dos hooks casi idénticos.
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

type Decision = 'approve' | 'reject'

export function useRegistrationDecision() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({ userId, decision }: { userId: string; decision: Decision }) => {
      const path =
        decision === 'approve'
          ? ('/api/v1/registrations/{user_id}/approve' as const)
          : ('/api/v1/registrations/{user_id}/reject' as const)
      const { error } = await api.POST(path, { params: { path: { user_id: userId } } })
      if (error) {
        throw new Error(
          errorDetail(error) ??
            (decision === 'approve'
              ? 'No se pudo aprobar el registro'
              : 'No se pudo rechazar el registro'),
        )
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pending-registrations'] })
      queryClient.invalidateQueries({ queryKey: ['companies-panel'] })
    },
  })
}

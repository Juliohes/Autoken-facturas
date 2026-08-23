import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useGlobalPending(cursor: string | null, enabled = true) {
  return useQuery({
    queryKey: ['platform-global-pending', cursor],
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/pending', {
        params: { query: { cursor: cursor ?? undefined, limit: 50 } },
      })
      if (error || !data) throw new Error('No se pudieron cargar los pendientes globales')
      return data
    },
  })
}

export function useGlobalPendingReview(
  tenantId: string | null,
  fileId: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: ['platform-global-pending-review', tenantId, fileId],
    enabled: enabled && Boolean(tenantId && fileId),
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/api/v1/platform/pending/{tenant_id}/{file_id}/review-readonly',
        { params: { path: { tenant_id: tenantId as string, file_id: fileId as string } } },
      )
      if (error || !data) throw new Error('No se pudo abrir el documento')
      return data
    },
  })
}

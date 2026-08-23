import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { components } from '../../api/schema'

export type UploadStatus = components['schemas']['UploadStatusOut']

export function useUploadStatus(fileId: string, enabled: boolean) {
  return useQuery<UploadStatus>({
    queryKey: ['upload-status', fileId],
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/uploads/{file_id}/status', {
        params: { path: { file_id: fileId } },
      })
      if (error || !data) throw new Error('No se pudo consultar el estado de la factura')
      return data
    },
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status === 'pending_ocr' || status === 'processing' ? 1000 : false
    },
  })
}

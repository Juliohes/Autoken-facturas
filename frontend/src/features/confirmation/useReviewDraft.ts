import { useMutation } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { components } from '../../api/schema'

export type ReviewDraftBody = components['schemas']['ReviewDraftIn']
export type ReviewDraftResult = components['schemas']['ReviewDraftOut']

export function useReviewDraft(fileId: string) {
  return useMutation<ReviewDraftResult, Error, ReviewDraftBody>({
    mutationFn: async (body) => {
      const { data, error } = await api.PUT('/api/v1/uploads/{file_id}/draft', {
        params: { path: { file_id: fileId } },
        body,
      })
      if (error || !data) {
        throw new Error('No se pudo guardar el borrador')
      }
      return data
    },
  })
}

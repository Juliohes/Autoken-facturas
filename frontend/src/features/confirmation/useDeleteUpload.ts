import { useMutation } from '@tanstack/react-query'

import { deleteUpload } from '../../api/client'

export class DeleteUploadError extends Error {
  constructor(readonly status: number, message: string) {
    super(message)
  }
}

export function useDeleteUpload(fileId: string) {
  return useMutation({
    mutationFn: async () => {
      const response = await deleteUpload(`/api/v1/uploads/${fileId}`)
      if (response.ok) return
      const body = await response.json().catch(() => undefined) as { detail?: unknown } | undefined
      const detail = typeof body?.detail === 'string' ? body.detail : 'No se pudo eliminar la factura.'
      throw new DeleteUploadError(response.status, detail)
    },
  })
}

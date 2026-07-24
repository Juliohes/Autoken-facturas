// Hook de subida (S2.2, C11-C14): sube el JPEG ya normalizado a `POST /uploads` (S2.1, sin ningún
// cambio de contrato) con `multipart/form-data`. `openapi-fetch` pasa un `FormData` tal cual sin
// serializarlo a JSON (ver `defaultBodySerializer`); el tipo generado espera el shape JSON del
// body, de ahí el cast documentado.
import { useMutation } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'
import { describeUploadError, type UploadErrorInfo } from './uploadErrors'

export class UploadCaptureError extends Error {
  readonly retryable: boolean
  constructor(info: UploadErrorInfo) {
    super(info.message)
    this.retryable = info.retryable
  }
}

export interface UploadCaptureInput {
  blob: Blob
  companyId: string
}

export function useUploadCapture() {
  return useMutation({
    mutationFn: async ({ blob, companyId }: UploadCaptureInput) => {
      const formData = new FormData()
      formData.append('file', blob, 'captura.jpg')
      formData.append('company_id', companyId)

      const { data, error, response } = await api.POST('/api/v1/uploads', {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- FormData real, no el shape JSON tipado (ver comentario de cabecera)
        body: formData as any,
      })
      if (error || !data) {
        throw new UploadCaptureError(describeUploadError(response.status, errorDetail(error)))
      }
      return data
    },
  })
}

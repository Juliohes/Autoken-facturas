// Hook de subida (S2.2, C11-C14): sube el JPEG ya normalizado con `multipart/form-data`. FastAPI
// describe las partes como `string` en OpenAPI, pero el navegador necesita un FormData real;
// `postMultipart` conserva auth y refresh sin convertir eso en un cast inseguro.
import { useMutation } from '@tanstack/react-query'

import { postMultipart } from '../../api/client'
import { errorDetail } from '../../api/errors'
import type { components } from '../../api/schema'
import { describeUploadError, type UploadErrorInfo } from './uploadErrors'
import type { Direction } from './types'

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

export interface UploadBatchCaptureInput {
  blobs: Blob[]
  companyId: string
  direction: Direction
}

type UploadResult = Pick<components['schemas']['UploadOut'], 'id'>

function isUploadResult(value: unknown): value is UploadResult {
  return value !== null && typeof value === 'object' && 'id' in value && typeof value.id === 'string'
}

async function readUploadResult(response: Response): Promise<UploadResult> {
  const body: unknown = await response.json().catch(() => undefined)
  if (!response.ok || !isUploadResult(body)) {
    throw new UploadCaptureError(describeUploadError(response.status, errorDetail(body)))
  }
  return body
}

export function useUploadCapture() {
  return useMutation({
    mutationFn: async ({ blob, companyId }: UploadCaptureInput) => {
      const formData = new FormData()
      formData.append('file', blob, 'captura.jpg')
      formData.append('company_id', companyId)

      return readUploadResult(await postMultipart('/api/v1/uploads', formData))
    },
  })
}

export function useUploadBatchCapture() {
  return useMutation({
    mutationFn: async ({ blobs, companyId, direction }: UploadBatchCaptureInput): Promise<UploadResult> => {
      const formData = new FormData()
      blobs.forEach((blob, index) => formData.append('files', blob, `pagina-${index + 1}.jpg`))
      formData.append('company_id', companyId)
      formData.append('direction', direction)

      return readUploadResult(await postMultipart('/api/v1/uploads/batch', formData))
    },
  })
}

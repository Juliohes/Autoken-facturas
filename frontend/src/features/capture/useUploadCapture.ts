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
  direction: Direction
  /** S6.14 C8: nitidez calculada en cliente (varianza del Laplaciano), solo telemetría del lado
   * servidor — nunca bloquea ni retrasa la subida. `null`/ausente cuando no hay análisis (p. ej.
   * selector de fichero sin cámara): se omite del `FormData`, no se manda un `0` inventado. */
  sharpnessScore?: number | null
}

export interface UploadBatchCaptureInput {
  blobs: Blob[]
  companyId: string
  direction: Direction
  /** Ver `UploadCaptureInput.sharpnessScore`; una factura de varias páginas no tiene una nitidez
   * de conjunto agregada hoy (decisión documentada en `CaptureScreen.tsx::sendPages`), así que en
   * la práctica este camino no la manda, pero el hook la admite igual por si un llamante futuro sí
   * calcula una. */
  sharpnessScore?: number | null
}

type UploadResult = Pick<components['schemas']['UploadOut'], 'id'>

interface DuplicateUploadResponse {
  duplicate_of: string
}

function isUploadResult(value: unknown): value is UploadResult {
  return value !== null && typeof value === 'object' && 'id' in value && typeof value.id === 'string'
}

function isDuplicateUploadResponse(value: unknown): value is DuplicateUploadResponse {
  return value !== null
    && typeof value === 'object'
    && 'duplicate_of' in value
    && typeof value.duplicate_of === 'string'
}

async function readUploadResult(response: Response): Promise<UploadResult> {
  const body: unknown = await response.json().catch(() => undefined)
  // El backend solo revela `duplicate_of` para el propio documento autorizado. Una respuesta de
  // subida perdida que se reintenta llega aquí como 409 y permite retomar el original sin duplicar.
  if (response.status === 409 && isDuplicateUploadResponse(body)) return { id: body.duplicate_of }
  if (!response.ok || !isUploadResult(body)) {
    throw new UploadCaptureError(describeUploadError(response.status, errorDetail(body)))
  }
  return body
}

// FormData solo admite `string`/`Blob`: la nitidez cruda (puede llevar decimales) viaja como
// string. `postMultipart` no pasa por el cliente OpenAPI generado (multipart sin tipar por
// endpoint), así que el campo se añade a mano aunque el schema.d.ts ya lo conozca. Ausente/`null`
// -> se omite el campo, nunca se manda un `0` inventado (S6.14 C8).
function appendSharpnessScore(formData: FormData, sharpnessScore: number | null | undefined) {
  if (typeof sharpnessScore === 'number') formData.append('sharpness_score', String(sharpnessScore))
}

export function useUploadCapture() {
  return useMutation({
    mutationFn: async ({ blob, companyId, direction, sharpnessScore }: UploadCaptureInput) => {
      const formData = new FormData()
      formData.append('file', blob, 'captura.jpg')
      formData.append('company_id', companyId)
      formData.append('direction', direction)
      appendSharpnessScore(formData, sharpnessScore)

      return readUploadResult(await postMultipart('/api/v1/uploads', formData))
    },
  })
}

export function useUploadBatchCapture() {
  return useMutation({
    mutationFn: async ({ blobs, companyId, direction, sharpnessScore }: UploadBatchCaptureInput): Promise<UploadResult> => {
      const formData = new FormData()
      blobs.forEach((blob, index) => formData.append('files', blob, `pagina-${index + 1}.jpg`))
      formData.append('company_id', companyId)
      formData.append('direction', direction)
      appendSharpnessScore(formData, sharpnessScore)

      return readUploadResult(await postMultipart('/api/v1/uploads/batch', formData))
    },
  })
}

// Hook de la confirmación (S2.4): envía `POST /uploads/{id}/confirm` con el body
// editado. En 4xx lanza un error con mensaje legible (C12) sin perder el estado.
import { useMutation } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { ConfirmBody } from './types'

/** Extrae un mensaje legible del cuerpo de error del backend (FastAPI `detail`). */
export function readableConfirmError(error: unknown): string {
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = (error as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    // Errores de validación (422): lista de `{msg}`; se muestra el primero.
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0]
      if (first && typeof first === 'object' && 'msg' in first) {
        const msg = (first as { msg: unknown }).msg
        if (typeof msg === 'string') return msg
      }
    }
  }
  return 'No se pudo confirmar la factura. Revisa los datos e inténtalo de nuevo.'
}

export function useConfirm(fileId: string) {
  return useMutation<{ id: string }, Error, ConfirmBody>({
    mutationFn: async (body: ConfirmBody) => {
      const { data, error } = await api.POST('/api/v1/uploads/{file_id}/confirm', {
        params: { path: { file_id: fileId } },
        body,
      })
      // El servidor reimpone las guardas (C12): un 4xx llega como `error`; se
      // traduce a un mensaje legible y se lanza para no navegar a éxito.
      if (error || !data) throw new Error(readableConfirmError(error))
      return data as unknown as { id: string }
    },
  })
}

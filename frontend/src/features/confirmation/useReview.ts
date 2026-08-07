// Hook de datos de la revisión (S2.4): consulta `GET /uploads/{id}/review` con el
// cliente tipado y devuelve la respuesta como `ReviewResponse` de dominio.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { ReviewResponse } from './types'

// Mismo texto que `service.PendingOcr` en el backend (invoicing/router.py): distingue el 409
// transitorio (worker OCR aún procesando, merece la pena reintentar) de uno permanente
// (`ocr_failed`, ya confirmado), que el backend responde con un `detail` distinto.
const PENDING_OCR_DETAIL = 'La factura todavía se está procesando con IA'

export class PendingOcrError extends Error {
  constructor() {
    super(PENDING_OCR_DETAIL)
    this.name = 'PendingOcrError'
  }
}

export function useReview(fileId: string) {
  return useQuery<ReviewResponse>({
    queryKey: ['review', fileId],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/uploads/{file_id}/review', {
        params: { path: { file_id: fileId } },
      })
      // 409 con el `detail` de `PendingOcr`: el worker aún no ha terminado, reintento de fondo.
      // Otro 409 (`ocr_failed`, ya confirmado) es permanente: cae al `throw` genérico de abajo,
      // sin esperar los reintentos.
      if (response?.status === 409 && (error as { detail?: unknown })?.detail === PENDING_OCR_DETAIL) {
        throw new PendingOcrError()
      }
      // `review` responde 403/404/409 sin datos (fichero ajeno / otro tenant / no confirmable):
      // se propaga como error para que la pantalla muestre el estado correspondiente (spec §5).
      if (error || !data) {
        throw new Error('No se pudieron cargar los datos de revisión')
      }
      // El endpoint responde `dict[str, object]`; el contrato real es `ReviewResponse`
      // (spec §2). Único punto de cast de la feature.
      return data as unknown as ReviewResponse
    },
    retry: (failureCount, err) => {
      if (err instanceof PendingOcrError) {
        // Reintenta de fondo sutilmente mientras procese con la IA (hasta 45 veces, i.e. ~67 segundos)
        return failureCount < 45
      }
      return false // No reintentar otros fallos (403, 404, etc.)
    },
    retryDelay: 1500, // Reintenta cada 1.5 segundos
  })
}

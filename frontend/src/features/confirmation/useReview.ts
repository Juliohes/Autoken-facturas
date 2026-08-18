// Hook de datos de la revisión (S2.4): consulta `GET /uploads/{id}/review` con el
// cliente tipado y devuelve la respuesta como `ReviewResponse` de dominio.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { ReviewResponse } from './types'

// Mismo texto que `service.PendingOcr` en el backend (invoicing/router.py): distingue el 409
// transitorio (worker OCR aún procesando, merece la pena reintentar) de uno permanente
// (`ocr_failed`, ya confirmado), que el backend responde con un `detail` distinto.
const PENDING_OCR_DETAIL = 'La factura todavía se está procesando con IA'

// Mismo texto que el backend responde para el estado `capture_unreadable` (S6.14 C7): la imagen en
// sí es el problema (extracción ilegible), no un campo dudoso concreto — se repite la foto, nunca
// se abre un formulario de revisión con campos vacíos.
const CAPTURE_UNREADABLE_DETAIL = 'La foto no se pudo leer, repite la captura'

export class PendingOcrError extends Error {
  constructor() {
    super(PENDING_OCR_DETAIL)
    this.name = 'PendingOcrError'
  }
}

/** A diferencia de `PendingOcrError`, permanente: no merece la pena reintentar leer la MISMA
 * imagen (S6.14 C7), solo repetir la captura. */
export class CaptureUnreadableError extends Error {
  constructor() {
    super(CAPTURE_UNREADABLE_DETAIL)
    this.name = 'CaptureUnreadableError'
  }
}

export function useReview(fileId: string) {
  return useQuery<ReviewResponse>({
    queryKey: ['review', fileId],
    queryFn: async () => {
      const { data, error, response } = await api.GET('/api/v1/uploads/{file_id}/review', {
        params: { path: { file_id: fileId } },
      })
      // 409 de captura ilegible: permanente, distinto del "ocr_failed" genérico (C7) — se detecta
      // ANTES que el `throw` genérico de abajo, igual que `PendingOcrError`.
      if (response?.status === 409 && (error as { detail?: unknown })?.detail === CAPTURE_UNREADABLE_DETAIL) {
        throw new CaptureUnreadableError()
      }
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
    // La aceptación de la subida es definitiva y el OCR no tiene fecha de caducidad visual. Solo
    // el 409 transitorio sigue consultando; 403/404/409 permanentes siguen sin reintento.
    retry: (_failureCount, err) => err instanceof PendingOcrError,
    retryDelay: 1500, // Reintenta cada 1.5 segundos
  })
}

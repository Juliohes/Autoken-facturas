// Hook de datos de la revisión (S2.4): consulta `GET /uploads/{id}/review` con el
// cliente tipado y devuelve la respuesta como `ReviewResponse` de dominio.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { ReviewResponse } from './types'

export function useReview(fileId: string) {
  return useQuery<ReviewResponse>({
    queryKey: ['review', fileId],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/uploads/{file_id}/review', {
        params: { path: { file_id: fileId } },
      })
      // `review` responde 403/404/409 sin datos (fichero ajeno / otro tenant / no
      // confirmable): se propaga como error para que la pantalla muestre el estado
      // correspondiente, no un formulario vacío editable (spec §5).
      if (error || !data) throw new Error('No se pudieron cargar los datos de revisión')
      // El endpoint responde `dict[str, object]`; el contrato real es `ReviewResponse`
      // (spec §2). Único punto de cast de la feature.
      return data as unknown as ReviewResponse
    },
  })
}

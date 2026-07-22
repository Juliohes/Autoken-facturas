// Hook de datos de la URL de descarga (reutiliza el endpoint de S2.7 tal cual, sin
// duplicar esa lógica). Separado de la presentación para que `InvoicesPanel` no
// llame a la API directamente (sin monolito).
import { useMutation } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useDownloadUrl() {
  return useMutation({
    mutationFn: async (uploadedFileId: string) => {
      const { data, error } = await api.GET('/api/v1/uploads/{file_id}/download-url', {
        params: { path: { file_id: uploadedFileId } },
      })
      if (error || !data) throw new Error('No se pudo obtener el enlace de descarga')
      return data.url
    },
  })
}

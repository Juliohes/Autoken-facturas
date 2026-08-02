// Hook de datos de la imagen original de una factura (2026-08-01): `GET
// /uploads/{file_id}/image`. Sustituye a `useDownloadUrl` (S2.7, URL firmada de MinIO): en el
// despliegue real MinIO nunca es alcanzable directamente desde el navegador (nunca se expone
// públicamente, aislamiento por tenant), así que ahora los bytes pasan por la API (que sí es
// pública) y aquí se convierten en una URL de objeto local para mostrarla en `InvoiceImageModal`.
import { useMutation } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useInvoiceImage() {
  return useMutation({
    mutationFn: async (uploadedFileId: string) => {
      const { data, error } = await api.GET('/api/v1/uploads/{file_id}/image', {
        params: { path: { file_id: uploadedFileId } },
        parseAs: 'blob',
      })
      if (error || !data) throw new Error('No se pudo cargar la imagen de la factura')
      return URL.createObjectURL(data as Blob)
    },
  })
}

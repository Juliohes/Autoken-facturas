// Hook de subida del logo de un tenant (2026-08-01, decisión de Julio): `POST
// /platform/tenants/logo`, multipart igual que `useUploadCapture` (S2.2) — mismo cast documentado
// ahí: `openapi-fetch` espera el shape JSON tipado por defecto, pero aquí se manda un `FormData`
// real tal cual.
import { useMutation } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function useUploadLogo() {
  return useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)

      const { data, error } = await api.POST('/api/v1/platform/tenants/logo', {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any -- FormData real, ver cabecera
        body: formData as any,
      })
      if (error || !data) throw new Error(errorDetail(error) ?? 'No se pudo subir el logo')
      return data
    },
  })
}

// Hook de datos de la foto original de una factura, desde el laboratorio de plataforma (S6.2,
// spec C2 "Ver"): `GET /platform/tenants/{tenant_id}/invoices/{file_id}/image`. Mismo patrón que
// `panel/useInvoiceImage` (bytes vía la API, nunca una URL de MinIO), variante platform-scoped
// porque una identidad `platform_admin` no tiene el `AuthContext` tenant-scoped que exige el
// endpoint del panel del tenant.
import { useMutation } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useTenantInvoiceImage() {
  return useMutation({
    mutationFn: async ({ tenantId, fileId }: { tenantId: string; fileId: string }) => {
      const { data, error } = await api.GET(
        '/api/v1/platform/tenants/{tenant_id}/invoices/{file_id}/image',
        { params: { path: { tenant_id: tenantId, file_id: fileId } }, parseAs: 'blob' },
      )
      if (error || !data) throw new Error('No se pudo cargar la imagen de la factura')
      return URL.createObjectURL(data as Blob)
    },
  })
}

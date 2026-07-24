// Hook de "Exportar" (S4.7): `POST /platform/tenants/{id}/export`. Genera el ZIP y devuelve una URL
// de descarga firmada; no invalida el listado (exportar no cambia nada visible en la tabla salvo
// `last_export_at`, que hoy no se muestra — spec S4.7 §0, decisión deliberada de alcance).
import { useMutation } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function useExportTenant() {
  return useMutation({
    mutationFn: async (tenantId: string) => {
      const { data, error } = await api.POST('/api/v1/platform/tenants/{tenant_id}/export', {
        params: { path: { tenant_id: tenantId } },
      })
      if (error || !data) throw new Error(errorDetail(error) ?? 'No se pudo exportar')
      return data
    },
  })
}

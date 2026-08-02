// Hook de datos del historial de ediciones de una empresa (2026-08-01): `GET
// /companies/{id}/history`. `enabled`: solo se pide cuando la fila lo tiene abierto (no en cada
// carga del panel, la mayoría de filas no se abren nunca).
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useCompanyHistory(companyId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['company-history', companyId],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/companies/{company_id}/history', {
        params: { path: { company_id: companyId } },
      })
      if (error || !data) throw new Error('No se pudo cargar el historial')
      return data
    },
    enabled,
  })
}

// Hook de datos de las empresas de la asesoría (para el filtro "empresa" del panel de facturas,
// S3.1, y el selector de empresa de la captura guiada, S2.2). Reutiliza el endpoint de S1.5
// (`GET /companies`, exclusivo de `tenant_admin`) tal cual, sin duplicar lógica. Vive en
// `features/companies/` (no en `panel/`, hallazgo de auditoría de arquitectura S2.2): es del
// contexto "empresa", reutilizado por dos features hermanas sin relación de dominio entre sí.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useCompanyOptions(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['companies'],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/companies')
      if (error || !data) throw new Error('No se pudieron cargar las empresas')
      return data
    },
    enabled: options.enabled ?? true,
  })
}

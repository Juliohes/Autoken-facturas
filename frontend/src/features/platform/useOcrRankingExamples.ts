// Hook de datos de los ejemplos concretos de un motor (2026-08-09, a petición de Julio: "más
// contexto, ver ejemplos concretos, no solo números"): `GET
// /platform/ocr-ranking/{engine}/examples`. `ExamplesModal` (único llamante) solo se monta ya con
// un motor elegido, así que a diferencia de otros hooks de esta feature no hace falta aceptar
// `null`/`enabled` (esas ramas nunca se ejercerían).
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useOcrRankingExamples(engine: string) {
  return useQuery({
    queryKey: ['ocr-ranking-examples', engine],
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/ocr-ranking/{engine}/examples', {
        params: { path: { engine } },
      })
      if (error || !data) throw new Error('No se pudieron cargar los ejemplos de este motor')
      return data
    },
  })
}

// Hook de lectura del ranking del benchmark real (S6.7): `GET /platform/benchmark/ranking`.
// A diferencia de `useOcrRanking` (S4.8, agregado por motor con un único ganador global), el
// backend ya devuelve dos vistas distintas -- por grupo de campo (C18, no hay un ganador único
// razonable entre CIF/NIF, importes y fecha) y por combinación variante+motor (C20) -- el
// componente solo las pinta, sin recalcular nada aquí.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

export function useBenchmarkRanking(enabled: boolean) {
  return useQuery({
    queryKey: ['benchmark-ranking'],
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/benchmark/ranking')
      if (error || !data) throw new Error('No se pudo cargar el ranking del benchmark')
      return data
    },
  })
}

// Hook de estado del lote de backfill del benchmark (S6.7 C10-C17): `GET
// /platform/benchmark/backfill/status`. Sondeo mientras hay un lote `running` -- `refetchInterval`
// como función que lee `query.state.data?.running`, la vía idiomática de TanStack Query v5 (ya es
// un `setTimeout` encadenado internamente, se reprograma tras cada respuesta; nunca un
// `setInterval` de intervalo fijo). Deja de sondear en cuanto el backend confirma que ya no corre
// nada (`running: false`), sea porque terminó o porque nunca se lanzó ninguno.
import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'

const POLL_INTERVAL_MS = 4000

export function useBenchmarkBackfillStatus(enabled: boolean) {
  return useQuery({
    queryKey: ['benchmark-backfill-status'],
    enabled,
    queryFn: async () => {
      const { data, error } = await api.GET('/api/v1/platform/benchmark/backfill/status')
      if (error || !data) throw new Error('No se pudo consultar el estado del lote')
      return data
    },
    refetchInterval: (query) => (query.state.data?.running ? POLL_INTERVAL_MS : false),
  })
}

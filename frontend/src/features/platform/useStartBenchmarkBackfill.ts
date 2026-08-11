// Hook de escritura para arrancar un lote de backfill del benchmark (S6.7 C10-C11): `POST
// /platform/benchmark/backfill`. El backend responde 200 si arranca de verdad, o 409 con el
// progreso del lote ya en marcha si había uno corriendo (mismo patrón ya usado por
// `invoice_intake.router` para `duplicate_of`) -- ese 409 NO es un fallo real, el panel se engancha
// al lote existente sin mostrar ningún error; solo un fallo de infraestructura genuino (network) o
// un 422 (interruptor del experimento apagado) se trata como error de verdad.
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { api } from '../../api/client'
import { errorDetail } from '../../api/errors'

export function useStartBenchmarkBackfill() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (limit: number) => {
      const { data, error, response } = await api.POST('/api/v1/platform/benchmark/backfill', {
        body: { limit },
      })
      if (response?.status === 409) {
        // Lote ya en marcha: ni error ni dato nuevo que guardar, el estado real llega por
        // `useBenchmarkBackfillStatus` (invalidado justo debajo).
        return { alreadyRunning: true as const }
      }
      if (error || !data) {
        throw new Error(errorDetail(error) ?? 'No se pudo iniciar el lote del benchmark')
      }
      return { alreadyRunning: false as const, ...data }
    },
    onSuccess: () => {
      // Recoge el progreso real de inmediato (200 recién arrancado, o 409 de uno ya en marcha) en
      // vez de esperar al primer sondeo automático.
      void queryClient.invalidateQueries({ queryKey: ['benchmark-backfill-status'] })
    },
  })
}

// Hook de datos del panel (S3.1): consulta `GET /reporting/invoices` paginado por
// cursor. Cada filtro nuevo reinicia la paginación (cambia la queryKey).
import { useInfiniteQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { PanelFilters, PanelPage } from './types'

type InvoicesPanelClient = {
  GET: (
    path: '/api/v1/reporting/invoices',
    options: { params: { query: PanelFilters & { cursor: string | undefined } } },
  ) => Promise<{ data?: PanelPage; error?: unknown }>
}

export function useInvoicesPanel(filters: PanelFilters) {
  return useInfiniteQuery({
    queryKey: ['invoices-panel', filters],
    queryFn: async ({ pageParam }: { pageParam: string | undefined }) => {
      const client = api as unknown as InvoicesPanelClient
      const { data, error } = await client.GET('/api/v1/reporting/invoices', {
        params: { query: { ...filters, cursor: pageParam } },
      })
      if (error || !data) throw new Error('No se pudo cargar el panel de facturas')
      return data
    },
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage: PanelPage) => lastPage.next_cursor ?? undefined,
  })
}

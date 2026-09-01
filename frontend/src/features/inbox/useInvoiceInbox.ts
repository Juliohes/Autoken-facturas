import { useQuery } from '@tanstack/react-query'

import { api } from '../../api/client'
import type { InboxResponse } from './types'

export const INBOX_QUERY_KEY = ['invoice-inbox'] as const

export function invoiceInboxQueryOptions(cursor: string | null) {
  return {
    queryKey: [...INBOX_QUERY_KEY, cursor] as const,
    queryFn: async (): Promise<InboxResponse> => {
      const { data, error } = await api.GET('/api/v1/invoices/inbox', {
        params: { query: { cursor, limit: 20 } },
      })
      if (error || !data) throw new Error('No se pudo cargar la bandeja de facturas')
      return data
    },
  }
}

export function useInvoiceInbox(cursor: string | null, enabled = true) {
  return useQuery({
    ...invoiceInboxQueryOptions(cursor),
    enabled,
    refetchInterval: (query) => (query.state.data?.summary?.processing ? 2000 : false),
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
  })
}

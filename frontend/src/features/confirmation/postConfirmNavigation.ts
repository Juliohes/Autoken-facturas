import type { QueryClient } from '@tanstack/react-query'

import {
  INBOX_QUERY_KEY,
  invoiceInboxQueryOptions,
} from '../inbox/useInvoiceInbox'
import type { InboxResponse, InboxItem } from '../inbox/types'

export async function navigateAfterConfirm(
  queryClient: QueryClient,
): Promise<InboxItem | null> {
  try {
    await queryClient.invalidateQueries({ queryKey: INBOX_QUERY_KEY })
    const snapshot = await queryClient.fetchQuery(invoiceInboxQueryOptions(null))
    return firstReadyInvoice(snapshot) ?? null
  } catch {
    // Si no podemos obtener la foto actual de la bandeja, no bloqueamos la salida del usuario.
    return null
  }
}

export function firstReadyInvoice(snapshot: InboxResponse) {
  return snapshot.items.find(
    (item) => item.status === 'ocr_done' || item.status === 'needs_review',
  )
}

import type { NavigateFunction } from 'react-router-dom'
import type { QueryClient } from '@tanstack/react-query'

import { ROUTES } from '../../app/routes'
import {
  INBOX_QUERY_KEY,
  invoiceInboxQueryOptions,
} from '../inbox/useInvoiceInbox'
import type { InboxResponse } from '../inbox/types'

export async function navigateAfterConfirm(
  queryClient: QueryClient,
  navigate: NavigateFunction,
): Promise<void> {
  try {
    await queryClient.invalidateQueries({ queryKey: INBOX_QUERY_KEY })
    const snapshot = await queryClient.fetchQuery(invoiceInboxQueryOptions(null))
    const next = firstReadyInvoice(snapshot)
    if (next) {
      navigate(ROUTES.confirmation(next.id), {
        state: { direction: next.direction ?? undefined },
      })
      return
    }
  } catch {
    // Si no podemos obtener la foto actual de la bandeja, no bloqueamos la salida del usuario.
  }
  navigate(ROUTES.inbox)
}

export function firstReadyInvoice(snapshot: InboxResponse) {
  return snapshot.items.find(
    (item) => item.status === 'ocr_done' || item.status === 'needs_review',
  )
}

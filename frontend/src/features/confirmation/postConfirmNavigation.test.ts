import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

import { ROUTES } from '../../app/routes'
import type { InboxResponse } from '../inbox/types'
import { firstReadyInvoice, navigateAfterConfirm } from './postConfirmNavigation'

const snapshot: InboxResponse = {
  items: [
    {
      id: 'current',
      status: 'confirmed',
      processing_stage: null,
      created_at: '2026-08-21T12:00:00Z',
      direction: 'recibida',
      page_count: 1,
      capture_session_id: null,
      capture_sequence: null,
      draft_updated_at: null,
    },
    {
      id: 'next',
      status: 'needs_review',
      processing_stage: null,
      created_at: '2026-08-21T11:00:00Z',
      direction: 'emitida',
      page_count: 1,
      capture_session_id: null,
      capture_sequence: null,
      draft_updated_at: null,
    },
  ],
  summary: { processing: 0, ready: 1, attention: 1 },
  next_cursor: null,
}

describe('navigateAfterConfirm (R-025)', () => {
  it('elige la primera factura revisable solo después de refrescar la bandeja', async () => {
    const queryClient = new QueryClient()
    const navigate = vi.fn()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    vi.spyOn(queryClient, 'fetchQuery').mockResolvedValue(snapshot)

    await navigateAfterConfirm(queryClient, navigate)

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['invoice-inbox'] })
    expect(navigate).toHaveBeenCalledWith(ROUTES.confirmation('next'), {
      state: { direction: 'emitida' },
    })
  })

  it('vuelve a Mis facturas cuando no quedan documentos revisables', async () => {
    const queryClient = new QueryClient()
    const navigate = vi.fn()
    vi.spyOn(queryClient, 'fetchQuery').mockResolvedValue({
      ...snapshot,
      items: [snapshot.items[0]],
      summary: { processing: 0, ready: 0, attention: 0 },
    })

    await navigateAfterConfirm(queryClient, navigate)

    expect(navigate).toHaveBeenCalledWith(ROUTES.inbox)
  })

  it('considera revisables solo ocr_done y needs_review', () => {
    expect(firstReadyInvoice({ ...snapshot, items: [{ ...snapshot.items[0], status: 'processing' }] })).toBeUndefined()
  })
})

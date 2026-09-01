import { QueryClient } from '@tanstack/react-query'
import { describe, expect, it, vi } from 'vitest'

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

describe('navigateAfterConfirm (R-052)', () => {
  it('devuelve la primera factura revisable solo después de refrescar la bandeja y no navega por sorpresa', async () => {
    const queryClient = new QueryClient()
    const navigate = vi.fn()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')
    vi.spyOn(queryClient, 'fetchQuery').mockResolvedValue(snapshot)

    const next = await navigateAfterConfirm(queryClient)

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['invoice-inbox'] })
    expect(next).toEqual(snapshot.items[1])
    expect(navigate).not.toHaveBeenCalled()
  })

  it('devuelve null cuando no quedan documentos revisables', async () => {
    const queryClient = new QueryClient()
    const navigate = vi.fn()
    vi.spyOn(queryClient, 'fetchQuery').mockResolvedValue({
      ...snapshot,
      items: [snapshot.items[0]],
      summary: { processing: 0, ready: 0, attention: 0 },
    })

    const next = await navigateAfterConfirm(queryClient)

    expect(next).toBeNull()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('considera revisables solo ocr_done y needs_review', () => {
    expect(firstReadyInvoice({ ...snapshot, items: [{ ...snapshot.items[0], status: 'processing' }] })).toBeUndefined()
  })
})

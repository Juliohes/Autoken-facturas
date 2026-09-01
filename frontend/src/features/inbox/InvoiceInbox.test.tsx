import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { InvoiceInbox } from './InvoiceInbox'

vi.mock('../../api/client', () => ({ api: { GET: vi.fn() } }))
vi.mock('../session/SessionProvider', () => ({
  useSession: vi.fn(() => ({ user: { feature_flags: { review_inbox_enabled: true } } })),
}))

const getMock = api.GET as unknown as Mock

function renderInbox(state?: Record<string, string>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter initialEntries={[{ pathname: '/mis-facturas', state }]}>
      <QueryClientProvider client={client}>
        <InvoiceInbox />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  getMock.mockReset()
})

describe('InvoiceInbox (R-020)', () => {
  it('R-052 C5: muestra el aviso de que la factura pendiente no se guardó tras eliminarla', async () => {
    getMock.mockResolvedValue({
      data: { items: [], summary: { processing: 0, ready: 0, attention: 0 }, next_cursor: null },
      error: undefined,
    })

    renderInbox({ message: 'La factura no se ha confirmado ni guardado.' })

    expect(await screen.findByRole('status')).toHaveTextContent('La factura no se ha confirmado ni guardado.')
  })

  it('muestra resumen y documentos operativos sin campos fiscales', async () => {
    getMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 'file-1',
            status: 'processing',
            processing_stage: 'primary_ocr',
            created_at: '2026-08-21T10:00:00Z',
            direction: 'recibida',
            page_count: 2,
            capture_session_id: null,
            capture_sequence: null,
            draft_updated_at: null,
          },
        ],
        summary: { processing: 1, ready: 2, attention: 3 },
        next_cursor: null,
      },
      error: undefined,
    })

    renderInbox()

    expect(await screen.findByText('Mis facturas')).toBeInTheDocument()
    expect(screen.getByText('Procesando OCR · 2 páginas')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.queryByText(/CIF|Proveedor|Importe|Número/)).not.toBeInTheDocument()
  })

  it('permite cargar la siguiente página con una petición agregada', async () => {
    getMock
      .mockResolvedValueOnce({
        data: {
          items: [],
          summary: { processing: 0, ready: 0, attention: 0 },
          next_cursor: 'cursor-2',
        },
        error: undefined,
      })
      .mockResolvedValueOnce({
        data: {
          items: [],
          summary: { processing: 0, ready: 0, attention: 0 },
          next_cursor: null,
        },
        error: undefined,
      })

    renderInbox()

    fireEvent.click(await screen.findByRole('button', { name: 'Cargar más' }))
    await waitFor(() => expect(getMock).toHaveBeenCalledTimes(2))
    expect(getMock.mock.calls[1][1]).toEqual({ params: { query: { cursor: 'cursor-2', limit: 20 } } })
  })

  it('no consulta la API cuando la bandeja está desactivada para el tenant', async () => {
    const { useSession } = await import('../session/SessionProvider')
    vi.mocked(useSession).mockReturnValue({
      user: { feature_flags: { review_inbox_enabled: false } },
    } as never)

    renderInbox()

    expect(await screen.findByText('La bandeja está temporalmente desactivada.')).toBeInTheDocument()
    expect(getMock).not.toHaveBeenCalled()
  })
})

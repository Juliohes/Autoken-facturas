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

    // R-VPS-v2 bloque 7: el H1 pasa de "Mis facturas" a "Pendientes" (deuda §1.1/§4.6, unifica
    // el nombre con el destino de navegación "Pendientes"). Bloque C (PROMPT-AUTOFACTU-AJUSTES-v3):
    // el estado se muestra sin caja (color+icono+texto, AA) y ya no se enseña el número de páginas.
    expect(await screen.findByText('Pendientes')).toBeInTheDocument()
    expect(screen.getByText('Procesando OCR')).toBeInTheDocument()
    expect(screen.queryByText(/páginas?/)).not.toBeInTheDocument()
    // Resumen sin "Listas" (bloque C.3): solo Procesando (1) y Revisar (3).
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.queryByText('Listas')).not.toBeInTheDocument()
    expect(screen.queryByText(/CIF|Proveedor|Importe|Número/)).not.toBeInTheDocument()
  })

  it('bloque C: "Revisar factura" en caja verde, "Eliminar" en caja roja, "Ver progreso" neutro', async () => {
    getMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 'reviewable-1',
            status: 'needs_review',
            processing_stage: null,
            created_at: '2026-08-21T10:00:00Z',
            direction: 'recibida',
            page_count: 1,
            capture_session_id: null,
            capture_sequence: null,
            draft_updated_at: null,
          },
        ],
        summary: { processing: 0, ready: 0, attention: 1 },
        next_cursor: null,
      },
      error: undefined,
    })

    renderInbox()

    const revisar = await screen.findByRole('link', { name: 'Revisar factura' })
    const eliminar = screen.getByRole('button', { name: 'Eliminar' })
    expect(revisar).toHaveClass('tn-inbox-action', 'tn-inbox-action-success')
    expect(eliminar).toHaveClass('tn-inbox-action', 'tn-inbox-action-danger')
  })

  it('bloque E: la fecha de subida de cada factura pendiente no muestra segundos', async () => {
    getMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 'file-1',
            status: 'processing',
            processing_stage: 'primary_ocr',
            created_at: '2026-08-21T10:00:45Z',
            direction: 'recibida',
            page_count: 1,
            capture_session_id: null,
            capture_sequence: null,
            draft_updated_at: null,
          },
        ],
        summary: { processing: 1, ready: 0, attention: 0 },
        next_cursor: null,
      },
      error: undefined,
    })

    renderInbox()

    const item = await screen.findByTestId('inbox-item')
    const timeNode = item.querySelector('time')
    expect(timeNode?.textContent ?? '').not.toMatch(/:\d{2}:\d{2}(\D|$)/)
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

  it('paso 9: no muestra una captura ilegible aunque llegara del backend (defensa frontend)', async () => {
    const { useSession } = await import('../session/SessionProvider')
    vi.mocked(useSession).mockReturnValue({
      user: { feature_flags: { review_inbox_enabled: true } },
    } as never)
    getMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 'unreadable-1',
            status: 'capture_unreadable',
            processing_stage: null,
            created_at: '2026-08-21T10:00:00Z',
            direction: 'recibida',
            page_count: 1,
            capture_session_id: null,
            capture_sequence: null,
            draft_updated_at: null,
          },
          {
            id: 'processing-1',
            status: 'processing',
            processing_stage: 'primary_ocr',
            created_at: '2026-08-21T09:00:00Z',
            direction: 'recibida',
            page_count: 1,
            capture_session_id: null,
            capture_sequence: null,
            draft_updated_at: null,
          },
        ],
        summary: { processing: 1, ready: 0, attention: 0 },
        next_cursor: null,
      },
      error: undefined,
    })

    renderInbox()

    const items = await screen.findAllByTestId('inbox-item')
    expect(items).toHaveLength(1)
    expect(screen.queryByText('Foto ilegible')).not.toBeInTheDocument()
    expect(screen.queryByText('Repetir foto')).not.toBeInTheDocument()
  })
})

// Tests de comportamiento de la pantalla de historial privado (S6.12). El cliente
// de API está mockeado: se inyecta la respuesta de `GET /invoices/history` de
// cada escenario (sin navegador ni backend reales; jsdom).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api, postJson } from '../../api/client'
import { InvoiceHistory } from './InvoiceHistory'
import type { HistoryEntry } from './types'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn() }, postJson: vi.fn(),
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const postJsonMock = postJson as unknown as AsyncMock

function makeEntry(over: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    id: 'inv-1',
    status: 'pending_ocr',
    created_at: '2026-08-14T10:30:00Z',
    // `direction` es requerida (nullable) en el contrato desde que se regeneró el OpenAPI en S6.14;
    // `null` representa el histórico previo a S6.13 (la pantalla pide la dirección, nunca la inventa).
    direction: null,
    ...over,
  }
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter><InvoiceHistory /></MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getMock.mockReset()
  postJsonMock.mockReset()
})

describe('InvoiceHistory (S6.12)', () => {
  it('S6.13 C2: muestra progreso, revisión o reintento seguro según el estado recuperable', async () => {
    getMock.mockResolvedValue({
      data: {
        entries: [
          makeEntry({ id: 'pending', status: 'pending_ocr' }),
          makeEntry({ id: 'processing', status: 'processing' }),
          makeEntry({ id: 'done', status: 'ocr_done', direction: 'emitida' }),
          makeEntry({ id: 'review', status: 'needs_review', direction: 'recibida' }),
          makeEntry({ id: 'failed', status: 'ocr_failed' }),
        ],
      },
      error: undefined,
    })
    postJsonMock.mockResolvedValue({ response: new Response(null, { status: 202 }) })
    renderScreen()
    const user = userEvent.setup()

    const rows = await screen.findAllByTestId('history-row')
    expect(within(rows[0]).getByRole('link', { name: 'Ver progreso' })).toHaveAttribute('href', '/confirmar/pending')
    expect(within(rows[1]).getByText('Procesando OCR')).toBeInTheDocument()
    expect(within(rows[2]).getByRole('link', { name: 'Revisar factura' })).toHaveAttribute('href', '/confirmar/done')
    expect(within(rows[3]).getByRole('link', { name: 'Revisar factura' })).toHaveAttribute('href', '/confirmar/review')

    await user.click(within(rows[4]).getByRole('button', { name: 'Reintentar lectura' }))

    expect(postJsonMock).toHaveBeenCalledWith('/api/v1/uploads/failed/retry-ocr')
  })
  // spec: docs/specs/S6.14-captura-alta-resolucion-y-confianza-nombre.md, C7
  it('S6.14 C7: un estado capture_unreadable muestra su propia etiqueta y enlaza directo a /capturar', async () => {
    getMock.mockResolvedValue({
      data: { entries: [makeEntry({ id: 'unreadable', status: 'capture_unreadable' })] },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    expect(within(rows[0]).getByText('No se pudo leer, repite la foto')).toBeInTheDocument()
    // Directo a /capturar (no a la revisión, para evitar el salto extra de C7).
    expect(within(rows[0]).getByRole('link', { name: /repetir/i })).toHaveAttribute('href', '/capturar')
  })

  it('C11: muestra los envíos privados con su fecha de creación y estado, sin PII ni dirección ausente', async () => {
    getMock.mockResolvedValue({
      data: {
        entries: [
          {
            ...makeEntry({ id: 'upload-1', status: 'pending_ocr', created_at: '2026-08-14T10:30:00Z' }),
            counterparty_name: 'Proveedor confidencial',
            counterparty_tax_id: 'B12345678',
          },
          makeEntry({ id: 'upload-2', status: 'ocr_failed', created_at: '2026-08-14T09:30:00Z' }),
        ],
      },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('Factura enviada')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Pendiente de OCR')).toBeInTheDocument()
    expect(within(rows[0]).getByText(/14\/8\/2026.*10:30/)).toBeInTheDocument()
    expect(within(rows[1]).getByText('OCR no completado')).toBeInTheDocument()
    expect(screen.queryByText(/Proveedor|B12345678|Recibida|Emitida/)).not.toBeInTheDocument()
  })

  it('C11: una respuesta degradada de más de veinte entradas no muestra una vigesimoprimera', async () => {
    getMock.mockResolvedValue({
      data: {
        entries: Array.from({ length: 21 }, (_, index) => makeEntry({ id: `upload-${index}` })),
      },
      error: undefined,
    })
    renderScreen()

    expect(await screen.findAllByTestId('history-row')).toHaveLength(20)
  })

  it('C11: lista vacía no conserva el corte obsoleto de siete días', async () => {
    getMock.mockResolvedValue({ data: { entries: [] }, error: undefined })
    renderScreen()

    expect(
      await screen.findByText('Todavía no has enviado ninguna factura.'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('history-list')).not.toBeInTheDocument()
  })

  it('C9: muestra "Cargando…" mientras carga', () => {
    getMock.mockReturnValue(new Promise(() => {})) // nunca resuelve: estado de carga estable
    renderScreen()

    expect(screen.getByText('Cargando…')).toBeInTheDocument()
  })

  it('C9: muestra un error legible si falla, sin datos a medias', async () => {
    getMock.mockResolvedValue({ data: undefined, error: { detail: 'boom' } })
    renderScreen()

    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudo cargar/i)
    expect(screen.queryByTestId('history-list')).not.toBeInTheDocument()
  })
})

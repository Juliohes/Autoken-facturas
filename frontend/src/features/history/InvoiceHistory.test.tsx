// Tests de comportamiento de la pantalla de historial (R-056 C9 + S6.12).
// Desde R-056, el Historial solo muestra facturas ya confirmadas (status=confirmed) de
// los últimos cuatro meses, en modo solo lectura — sin acciones ni enlaces a revisión.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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
    // R-056 C9: el historial solo muestra facturas confirmadas.
    status: 'confirmed',
    created_at: '2026-08-14T10:30:00Z',
    direction: 'recibida',
    invoice_number: null,
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
  // R-056 C9: el historial es de solo lectura — muestra facturas confirmadas sin acciones.
  it('R-056 C9: muestra facturas confirmadas en modo solo lectura, sin enlaces de revisión', async () => {
    getMock.mockResolvedValue({
      data: {
        entries: [
          makeEntry({ id: 'conf-1', created_at: '2026-08-14T10:30:00Z', direction: 'emitida' }),
          makeEntry({ id: 'conf-2', created_at: '2026-08-13T09:00:00Z', direction: 'recibida' }),
        ],
      },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    expect(rows).toHaveLength(2)
    // Solo lectura: no hay enlaces ni botones de acción en el historial.
    expect(within(rows[0]).queryByRole('link')).not.toBeInTheDocument()
    expect(within(rows[0]).queryByRole('button')).not.toBeInTheDocument()
    expect(within(rows[0]).getByText('Factura enviada')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Confirmada')).toBeInTheDocument()
    // Paso 8, ajustes UI: "Solo lectura" ya no aparece en ninguna fila.
    expect(within(rows[0]).queryByText('Solo lectura')).not.toBeInTheDocument()
  })

  it('paso 8: muestra el número de factura cuando el backend lo envía', async () => {
    getMock.mockResolvedValue({
      data: { entries: [makeEntry({ id: 'conf-1', invoice_number: 'FE-2026-004821' })] },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    expect(within(rows[0]).getByText('Factura Nº FE-2026-004821')).toBeInTheDocument()
    expect(within(rows[0]).queryByText('Factura enviada')).not.toBeInTheDocument()
  })

  it('paso 8: sin número de factura, muestra un texto neutro en vez de inventar uno', async () => {
    getMock.mockResolvedValue({
      data: { entries: [makeEntry({ id: 'conf-1', invoice_number: null })] },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    expect(within(rows[0]).getByText('Factura enviada')).toBeInTheDocument()
  })

  it('C11: muestra los envíos confirmados con su fecha y estado, sin PII', async () => {
    getMock.mockResolvedValue({
      data: {
        entries: [
          makeEntry({ id: 'upload-1', status: 'confirmed', created_at: '2026-08-14T10:30:00Z' }),
          makeEntry({ id: 'upload-2', status: 'confirmed', created_at: '2026-08-14T09:30:00Z' }),
        ],
      },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    expect(rows).toHaveLength(2)
    expect(within(rows[0]).getByText('Factura enviada')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Confirmada')).toBeInTheDocument()
    expect(within(rows[0]).getByText(/14\/8\/2026.*10:30/)).toBeInTheDocument()
    // PII: no debe aparecer nombre de empresa ni CIF.
    expect(screen.queryByText(/B12345678|Proveedor/)).not.toBeInTheDocument()
  })

  it('C11: una respuesta de más de veinte entradas no muestra una vigesimoprimera', async () => {
    getMock.mockResolvedValue({
      data: {
        entries: Array.from({ length: 21 }, (_, index) => makeEntry({ id: `upload-${index}` })),
      },
      error: undefined,
    })
    renderScreen()

    expect(await screen.findAllByTestId('history-row')).toHaveLength(20)
  })

  it('C11: lista vacía muestra el mensaje de historial vacío de los últimos cuatro meses', async () => {
    getMock.mockResolvedValue({ data: { entries: [] }, error: undefined })
    renderScreen()

    expect(
      await screen.findByText(/todavía no tienes facturas confirmadas en los últimos cuatro meses/i),
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

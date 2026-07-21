// Tests de comportamiento de la pantalla de historial (S2.6), C7-C9. El cliente
// de API está mockeado: se inyecta la respuesta de `GET /invoices/history` de
// cada escenario (sin navegador ni backend reales; jsdom).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { InvoiceHistory } from './InvoiceHistory'
import type { HistoryEntry } from './types'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock

function makeEntry(over: Partial<HistoryEntry> = {}): HistoryEntry {
  return {
    id: 'inv-1',
    issue_date: '2026-07-20',
    direction: 'recibida',
    counterparty_tax_id: 'B12345678',
    counterparty_name: 'Proveedor SL',
    counterparty_cif_status: 'valid',
    total_amount: '121.00',
    confirmed_at: '2026-07-21T10:00:00Z',
    ...over,
  }
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <InvoiceHistory />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getMock.mockReset()
})

describe('InvoiceHistory (S2.6)', () => {
  it('C7: muestra una fila por factura con contraparte, fecha, total y estado', async () => {
    getMock.mockResolvedValue({
      data: {
        entries: [
          makeEntry({ id: 'inv-1', counterparty_name: 'Reciente SL', confirmed_at: '2026-07-21T10:00:00Z' }),
          makeEntry({ id: 'inv-2', counterparty_name: 'Antigua SL', confirmed_at: '2026-07-15T10:00:00Z' }),
        ],
      },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    expect(rows).toHaveLength(2)
    // La más reciente arriba (el backend ya ordena; la pantalla no reordena).
    expect(within(rows[0]).getByText('Reciente SL')).toBeInTheDocument()
    expect(within(rows[0]).getByText('121.00')).toBeInTheDocument()
    expect(within(rows[0]).getByText('valid')).toBeInTheDocument()
    expect(within(rows[0]).getByText(/2026-07-20/)).toBeInTheDocument()
    expect(within(rows[1]).getByText('Antigua SL')).toBeInTheDocument()
  })

  it('C8: lista vacía muestra el mensaje de "no hay facturas", no una tabla vacía', async () => {
    getMock.mockResolvedValue({ data: { entries: [] }, error: undefined })
    renderScreen()

    expect(
      await screen.findByText('No hay facturas en los últimos 7 días.'),
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

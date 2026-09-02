// Tests de comportamiento de la pantalla de historial (R-056 C9 + S6.12).
// Desde R-056, el Historial solo muestra facturas ya confirmadas (status=confirmed) de
// los últimos cuatro meses, en modo solo lectura — sin acciones ni enlaces a revisión.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
    invoice_date: null,
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
    expect(within(rows[0]).getByText('Sin número')).toBeInTheDocument()
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
    expect(within(rows[0]).queryByText('Sin número')).not.toBeInTheDocument()
  })

  it('bloque D: sin número de factura, muestra "Sin número" en vez de inventar uno', async () => {
    getMock.mockResolvedValue({
      data: { entries: [makeEntry({ id: 'conf-1', invoice_number: null })] },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    expect(within(rows[0]).getByText('Sin número')).toBeInTheDocument()
  })

  it('bloque D: muestra la fecha de factura etiquetada, con "Sin fecha" si falta', async () => {
    getMock.mockResolvedValue({
      data: {
        entries: [
          makeEntry({ id: 'conf-1', invoice_date: '2026-03-15' }),
          makeEntry({ id: 'conf-2', invoice_date: null }),
        ],
      },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    expect(within(rows[0]).getByText('Fecha factura: 15/03/2026')).toBeInTheDocument()
    expect(within(rows[1]).getByText('Sin fecha')).toBeInTheDocument()
  })

  it('bloque D: etiqueta la fecha de subida con "Subida:"', async () => {
    getMock.mockResolvedValue({
      data: { entries: [makeEntry({ id: 'conf-1', created_at: '2026-08-14T10:30:00Z' })] },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    expect(within(rows[0]).getByText(/^Subida: /)).toBeInTheDocument()
  })

  it('bloque E: la fecha de subida no muestra segundos', async () => {
    getMock.mockResolvedValue({
      data: { entries: [makeEntry({ id: 'conf-1', created_at: '2026-08-14T10:30:45Z' })] },
      error: undefined,
    })
    renderScreen()

    const rows = await screen.findAllByTestId('history-row')
    const uploadDate = within(rows[0]).getByText(/^Subida: /)
    expect(uploadDate.textContent).not.toMatch(/:\d{2}:\d{2}(\D|$)/)
  })

  it('bloque D: el desplegable de periodo muestra Total/Este mes/Este trimestre/Este año, con Total por defecto', async () => {
    getMock.mockResolvedValue({ data: { entries: [makeEntry()], count: 1 }, error: undefined })
    renderScreen()

    await screen.findAllByTestId('history-row')
    const select = screen.getByRole('combobox', { name: 'Periodo' })
    expect(select).toHaveValue('total')
    expect(screen.getByRole('option', { name: 'Total' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Este mes' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Este trimestre' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Este año' })).toBeInTheDocument()
  })

  it('bloque D: muestra el número de facturas del filtro (count) junto al desplegable', async () => {
    getMock.mockResolvedValue({ data: { entries: [makeEntry()], count: 7 }, error: undefined })
    renderScreen()

    expect(await screen.findByText('7 facturas')).toBeInTheDocument()
  })

  it('bloque D: al cambiar de periodo, vuelve a pedir el historial con ese period', async () => {
    getMock.mockResolvedValue({ data: { entries: [makeEntry()], count: 1 }, error: undefined })
    renderScreen()
    const user = userEvent.setup()

    await screen.findAllByTestId('history-row')
    await user.selectOptions(screen.getByRole('combobox', { name: 'Periodo' }), 'month')

    await waitFor(() => {
      const lastCall = getMock.mock.calls.at(-1) as unknown as [string, { params: { query: { period: string } } }]
      expect(lastCall[1].params.query.period).toBe('month')
    })
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
    expect(within(rows[0]).getByText('Sin número')).toBeInTheDocument()
    expect(within(rows[0]).getByText('Confirmada')).toBeInTheDocument()
    expect(within(rows[0]).getByText(/14\/8\/26.*10:30/)).toBeInTheDocument()
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

  it('deja hueco al final para que la última factura no quede tapada por la barra inferior fija', async () => {
    getMock.mockResolvedValue({
      data: { entries: [makeEntry({ id: 'conf-1' })] },
      error: undefined,
    })
    renderScreen()

    const list = await screen.findByTestId('history-list')
    expect(list.closest('section')).toHaveClass('tn-scroll-clear-bottom-nav')
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

// Tests de comportamiento de la pantalla de historial (S2.6), C7-C9. El cliente
// de API está mockeado: se inyecta la respuesta de `GET /invoices/history` de
// cada escenario (sin navegador ni backend reales; jsdom).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { useSession } from '../session/SessionProvider'
import { InvoiceHistory } from './InvoiceHistory'
import type { HistoryEntry } from './types'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn() },
}))

// Experimento 2026-08-01 (rama experiment/setex-user-ui-v1): `InvoiceHistory` ahora consulta el
// rol de sesión para decidir su aspecto (SETEX claro para `user`, oscuro de siempre para
// `tenant_admin`) — mismo patrón de mock ya usado en `CaptureScreen.test.tsx`.
vi.mock('../session/SessionProvider', () => ({
  useSession: vi.fn(),
}))
const useSessionMock = vi.mocked(useSession)

const TENANT_ADMIN_SESSION = {
  status: 'authenticated' as const,
  user: {
    id: 't1',
    email: 'ana@ilex.es',
    role: 'tenant_admin' as const,
    tenant: 'ilex',
    company: null,
    is_admin_tech: false,
  },
  login: vi.fn(),
  logout: vi.fn(),
}

const USER_SESSION = {
  status: 'authenticated' as const,
  user: {
    id: 'u1',
    email: 'ana@ilex.es',
    role: 'user' as const,
    tenant: 'ilex',
    company: { id: 'c1', name: 'Empresa Uno' },
    is_admin_tech: false,
  },
  login: vi.fn(),
  logout: vi.fn(),
}

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
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <InvoiceHistory />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  getMock.mockReset()
  useSessionMock.mockReturnValue(TENANT_ADMIN_SESSION)
})

describe('InvoiceHistory (S2.6) — tenant_admin (aspecto oscuro de siempre)', () => {
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

describe('InvoiceHistory — experimento SETEX (rol user)', () => {
  beforeEach(() => {
    useSessionMock.mockReturnValue(USER_SESSION)
  })

  it('muestra proveedor, tipo de identificador, fecha, total con coma y compra/venta', async () => {
    getMock.mockResolvedValue({
      data: {
        entries: [
          makeEntry({
            id: 'inv-1',
            counterparty_name: 'Proveedor Autónomo',
            counterparty_tax_id: '12345678Z',
            total_amount: '121.00',
            direction: 'emitida',
          }),
        ],
      },
      error: undefined,
    })
    renderScreen()

    const row = await screen.findByTestId('history-row')
    expect(within(row).getByText('Proveedor Autónomo')).toBeInTheDocument()
    expect(within(row).getByText('NIF')).toBeInTheDocument()
    expect(within(row).getByText('121,00')).toBeInTheDocument()
    expect(within(row).getByText('↑ Emitida')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Facturas' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '← Volver a capturar' })).toBeInTheDocument()
  })

  it('lista vacía muestra el microcopy literal de SETEX, dentro de la tarjeta con cabecera', async () => {
    getMock.mockResolvedValue({ data: { entries: [] }, error: undefined })
    renderScreen()

    expect(await screen.findByText('Sin facturas en los últimos 7 días.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Facturas' })).toBeInTheDocument()
  })
})

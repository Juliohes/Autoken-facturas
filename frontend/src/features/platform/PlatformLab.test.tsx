// Tests de comportamiento de `PlatformLab` (S6.2, spec docs/specs/S6.2-laboratorio-ocr-admin-tech.md,
// C1-C2/C6-C13). Cliente de API mockeado; sesión mockeada para controlar `user.is_admin_tech`, mismo
// patrón que `OcrRanking.test.tsx`/`PlatformSettings.test.tsx`.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { useSession } from '../session/SessionProvider'
import { PlatformLab } from './PlatformLab'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn() },
}))
vi.mock('../session/SessionProvider', () => ({
  useSession: vi.fn(),
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const useSessionMock = vi.mocked(useSession)

function asUser(isAdminTech: boolean) {
  useSessionMock.mockReturnValue({
    status: 'authenticated',
    user: {
      id: 'p1',
      email: 'julio@autoken.es',
      role: 'platform_admin',
      tenant: null,
      company: null,
      is_admin_tech: isAdminTech,
    },
    login: vi.fn(),
    logout: vi.fn(),
  })
}

const TENANTS = [
  {
    id: 't-ilex',
    slug: 'ilex',
    name: 'ILEX Asesoría',
    status: 'active',
    is_demo: false,
    created_at: '2026-01-01T00:00:00Z',
    custom_domain: null,
  },
]

const INVOICE_ROW = {
  id: 'inv-1',
  uploaded_file_id: 'file-1',
  company_name: 'Mi Empresa SL',
  counterparty_name: 'Proveedor SA',
  issue_date: '2026-05-10',
  total_amount: '121.00',
  confirmed_at: '2026-05-11T10:00:00Z',
}

const LAB_DETAIL = {
  reading_1: {
    raw: { total_amount: 121, tax_ids: [{ value: 'B06183446' }] },
    engine: 'gemini-3-flash',
    model: 'gemini-3-flash-001',
  },
  reading_2: {
    fields: { total_amount: '121.00' },
    confidences: { total_amount: 'alta' },
    counterparty_verdict: { status: 'valid', name_match: true, official_name: null },
    own: { cif: 'B00000000', name: 'Mi Empresa SL' },
    warnings: [],
    blocking_reasons: [],
  },
  reading_3: {
    invoice: { total_amount: '121.00' },
    corrections: [],
    has_corrections: false,
  },
  ranking: [],
  ranking_available: false,
}

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PlatformLab />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getMock.mockReset()
})

describe('PlatformLab (S6.2)', () => {
  it('C1: un platform_admin sin el flag ve "sin acceso", nunca el selector de tenants', () => {
    asUser(false)

    renderScreen()

    expect(screen.getByRole('alert')).toHaveTextContent(/no tienes acceso/i)
    expect(screen.queryByLabelText(/tenant/i)).not.toBeInTheDocument()
    expect(getMock).not.toHaveBeenCalled() // evita el GET que el backend rechazaría con 403
  })

  it('C2: con el flag, elegir un tenant lista sus facturas confirmadas con Ver/Laboratorio', async () => {
    asUser(true)
    getMock.mockImplementation((path: string) => {
      if (path.includes('/platform/tenants') && !path.includes('/invoices')) {
        return Promise.resolve({ data: TENANTS, error: undefined })
      }
      if (path.includes('/invoices') && !path.includes('/lab')) {
        return Promise.resolve({ data: [INVOICE_ROW], error: undefined })
      }
      return Promise.resolve({ data: {}, error: undefined })
    })
    const user = userEvent.setup()
    renderScreen()

    const select = await screen.findByLabelText(/tenant/i)
    await screen.findByRole('option', { name: 'ILEX Asesoría' }) // espera a que carguen los tenants
    await user.selectOptions(select, 't-ilex')

    const row = await screen.findByText('Proveedor SA')
    const tr = row.closest('tr') as HTMLElement
    expect(within(tr).getByRole('button', { name: 'Ver' })).toBeInTheDocument()
    expect(within(tr).getByRole('button', { name: 'Laboratorio' })).toBeInTheDocument()
  })

  it('C11/C13: el detalle del laboratorio muestra "sin correcciones" y "sin comparativa" cuando no las hay', async () => {
    asUser(true)
    getMock.mockImplementation((path: string) => {
      if (path.includes('/platform/tenants') && !path.includes('/invoices')) {
        return Promise.resolve({ data: TENANTS, error: undefined })
      }
      if (path.includes('/lab')) {
        return Promise.resolve({ data: LAB_DETAIL, error: undefined })
      }
      if (path.includes('/invoices')) {
        return Promise.resolve({ data: [INVOICE_ROW], error: undefined })
      }
      return Promise.resolve({ data: {}, error: undefined })
    })
    const user = userEvent.setup()
    renderScreen()

    const select = await screen.findByLabelText(/tenant/i)
    await screen.findByRole('option', { name: 'ILEX Asesoría' }) // espera a que carguen los tenants
    await user.selectOptions(select, 't-ilex')
    await user.click(await screen.findByRole('button', { name: 'Laboratorio' }))

    await waitFor(() => {
      expect(screen.getByText(/sin correcciones/i)).toBeInTheDocument()
    })
    expect(screen.getByText(/sin datos de comparativa/i)).toBeInTheDocument()
    // Las 3 lecturas están presentes (aunque sea con datos mínimos del mock).
    expect(screen.getByTestId('lab-reading-1')).toBeInTheDocument()
    expect(screen.getByTestId('lab-reading-2')).toBeInTheDocument()
    expect(screen.getByTestId('lab-reading-3')).toBeInTheDocument()
  })

  it('la comparativa con filas las muestra ordenadas, no el mensaje de "sin datos"', async () => {
    asUser(true)
    getMock.mockImplementation((path: string) => {
      if (path.includes('/platform/tenants') && !path.includes('/invoices')) {
        return Promise.resolve({ data: TENANTS, error: undefined })
      }
      if (path.includes('/lab')) {
        return Promise.resolve({
          data: {
            ...LAB_DETAIL,
            ranking: [
              { engine: 'gemini-3-flash', model: 'x', reading: {}, score: 90 },
              { engine: 'mistral-ocr-4', model: 'y', reading: {}, score: 10 },
            ],
            ranking_available: true,
          },
          error: undefined,
        })
      }
      if (path.includes('/invoices')) {
        return Promise.resolve({ data: [INVOICE_ROW], error: undefined })
      }
      return Promise.resolve({ data: {}, error: undefined })
    })
    const user = userEvent.setup()
    renderScreen()

    const select = await screen.findByLabelText(/tenant/i)
    await screen.findByRole('option', { name: 'ILEX Asesoría' }) // espera a que carguen los tenants
    await user.selectOptions(select, 't-ilex')
    await user.click(await screen.findByRole('button', { name: 'Laboratorio' }))

    expect(await screen.findByText('gemini-3-flash')).toBeInTheDocument()
    expect(screen.getByText('mistral-ocr-4')).toBeInTheDocument()
    expect(screen.queryByText(/sin datos de comparativa/i)).not.toBeInTheDocument()
  })
})

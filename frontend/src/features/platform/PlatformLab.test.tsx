// Tests de comportamiento de `PlatformLab` (S6.2, spec docs/specs/S6.2-laboratorio-ocr-admin-tech.md,
// C1-C2/C6-C13). Cliente de API mockeado; sesión mockeada para controlar `user.is_admin_tech`, mismo
// patrón que `OcrRanking.test.tsx`/`PlatformSettings.test.tsx`.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
    field_comparison: [
      { field: 'total_amount', column_2: '121.00', column_3: '121.00', match: true },
      { field: 'invoice_number', column_2: null, column_3: null, match: null },
    ],
    tax_lines_comparison: {
      column_2: [{ iva_pct: '21', base: '100.00', cuota: '21.00' }],
      column_3: [{ iva_pct: '21', base: '100.00', cuota: '21.00' }],
      match: true,
    },
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

  it('S6.6 C11/S6.2 C13: la tabla unificada se pinta siempre (sin mensaje "sin correcciones" aparte) y la comparativa sigue avisando cuando no hay datos', async () => {
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

    const dialog = await screen.findByRole('dialog', { name: 'Laboratorio de esta factura' })
    // La tabla unificada muestra el campo con acierto (total_amount) y también "Tramos de IVA".
    await waitFor(() => {
      expect(within(dialog).getByText('Total')).toBeInTheDocument()
    })
    expect(within(dialog).getByText('Tramos de IVA')).toBeInTheDocument()
    expect(within(dialog).queryByText(/sin correcciones/i)).not.toBeInTheDocument()
    expect(within(dialog).getByText(/sin datos de comparativa/i)).toBeInTheDocument()
    // Las 3 lecturas están presentes (aunque sea con datos mínimos del mock).
    expect(within(dialog).getByTestId('lab-reading-1')).toBeInTheDocument()
    expect(within(dialog).getByTestId('lab-reading-2')).toBeInTheDocument()
    expect(within(dialog).getByTestId('lab-reading-3')).toBeInTheDocument()
  })

  it('S6.6 C6-C8: el badge de acierto es verde si coincide, rojo si no, gris si no es comparable', async () => {
    asUser(true)
    getMock.mockImplementation((path: string) => {
      if (path.includes('/platform/tenants') && !path.includes('/invoices')) {
        return Promise.resolve({ data: TENANTS, error: undefined })
      }
      if (path.includes('/lab')) {
        return Promise.resolve({
          data: {
            ...LAB_DETAIL,
            reading_3: {
              invoice: { total_amount: '199.00' },
              field_comparison: [
                { field: 'total_amount', column_2: '121.00', column_3: '199.00', match: false },
                { field: 'issue_date', column_2: '2026-05-10', column_3: '2026-05-10', match: true },
                { field: 'invoice_number', column_2: null, column_3: null, match: null },
              ],
              tax_lines_comparison: LAB_DETAIL.reading_3.tax_lines_comparison,
            },
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
    await screen.findByRole('option', { name: 'ILEX Asesoría' })
    await user.selectOptions(select, 't-ilex')
    await user.click(await screen.findByRole('button', { name: 'Laboratorio' }))

    const dialog = await screen.findByRole('dialog', { name: 'Laboratorio de esta factura' })
    await within(dialog).findAllByLabelText('fallo')
    expect(within(dialog).getAllByLabelText('fallo')).toHaveLength(1)
    expect(within(dialog).getAllByLabelText('acierto').length).toBeGreaterThanOrEqual(1)
    expect(within(dialog).getAllByLabelText('no comparable')).toHaveLength(1)
    // El campo corregido lleva un fondo distinto (C7: "el ojo va solo a lo que falló").
    const totalCells = within(dialog).getAllByText('Total')
    const totalRow = totalCells[totalCells.length - 1].closest('tr') as HTMLElement
    expect(totalRow.className).toContain('bg-red-950')
  })

  it('el laboratorio se abre en una ventana emergente, no debajo de la tabla, y se puede cerrar', async () => {
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
    await screen.findByRole('option', { name: 'ILEX Asesoría' })
    await user.selectOptions(select, 't-ilex')
    // Antes de abrirlo, no hay ningún diálogo en pantalla.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: 'Laboratorio' }))

    const dialog = await screen.findByRole('dialog', { name: 'Laboratorio de esta factura' })
    expect(dialog).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Cerrar' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
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

  it('2026-08-10: la tabla de facturas del tenant se puede redimensionar y ordenar por cabecera', async () => {
    asUser(true)
    getMock.mockImplementation((path: string) => {
      if (path.includes('/platform/tenants') && !path.includes('/invoices')) {
        return Promise.resolve({ data: TENANTS, error: undefined })
      }
      if (path.includes('/invoices') && !path.includes('/lab')) {
        return Promise.resolve({
          data: [
            { ...INVOICE_ROW, id: 'inv-1', company_name: 'Zeta SL' },
            { ...INVOICE_ROW, id: 'inv-2', company_name: 'Alfa SL' },
          ],
          error: undefined,
        })
      }
      return Promise.resolve({ data: {}, error: undefined })
    })
    const user = userEvent.setup()
    renderScreen()

    const select = await screen.findByLabelText(/tenant/i)
    await screen.findByRole('option', { name: 'ILEX Asesoría' })
    await user.selectOptions(select, 't-ilex')
    await screen.findAllByTestId('lab-invoice-row')

    await user.click(screen.getByRole('button', { name: 'Empresa' }))
    const names = screen
      .getAllByTestId('lab-invoice-row')
      .map((row) => within(row).getAllByRole('cell')[0].textContent)
    expect(names).toEqual(['Alfa SL', 'Zeta SL'])

    const handle = screen.getByRole('separator', { name: 'Redimensionar columna Empresa' })
    const header = screen.getByRole('button', { name: 'Empresa' }).closest('th') as HTMLElement
    const startWidth = Number(header.style.width.replace('px', ''))
    fireEvent.mouseDown(handle, { clientX: 100 })
    fireEvent.mouseMove(document, { clientX: 150 })
    fireEvent.mouseUp(document, { clientX: 150 })
    expect(Number(header.style.width.replace('px', ''))).toBe(startWidth + 50)
  })

  it('2026-08-10: la tabla unificada (Lectura 3) del laboratorio se puede ordenar por cabecera', async () => {
    asUser(true)
    getMock.mockImplementation((path: string) => {
      if (path.includes('/platform/tenants') && !path.includes('/invoices')) {
        return Promise.resolve({ data: TENANTS, error: undefined })
      }
      if (path.includes('/lab')) {
        return Promise.resolve({
          data: {
            ...LAB_DETAIL,
            reading_3: {
              invoice: { total_amount: '121.00' },
              field_comparison: [
                { field: 'zeta_field', column_2: 'a', column_3: 'b', match: false },
                { field: 'alfa_field', column_2: 'c', column_3: 'd', match: true },
              ],
              tax_lines_comparison: { column_2: [], column_3: [], match: true },
            },
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
    await screen.findByRole('option', { name: 'ILEX Asesoría' })
    await user.selectOptions(select, 't-ilex')
    await user.click(await screen.findByRole('button', { name: 'Laboratorio' }))

    const dialog = await screen.findByRole('dialog', { name: 'Laboratorio de esta factura' })
    await user.click(within(dialog).getByRole('button', { name: 'Campo' }))

    const rows = within(dialog).getAllByRole('row').filter((r) => within(r).queryAllByRole('cell').length > 0)
    const fields = rows.map((row) => within(row).getAllByRole('cell')[0].textContent)
    // "Tramos de IVA" es una fila manual, siempre al final, ajena al orden de los campos (C9).
    expect(fields).toEqual(['alfa_field', 'zeta_field', 'Tramos de IVA'])
  })

  it('2026-08-10: la comparativa de modelos se puede ordenar por puntuación', async () => {
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
              { engine: 'b-engine', model: 'y', reading: {}, score: 9 },
              { engine: 'a-engine', model: 'x', reading: {}, score: 2 },
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
    await screen.findByRole('option', { name: 'ILEX Asesoría' })
    await user.selectOptions(select, 't-ilex')
    await user.click(await screen.findByRole('button', { name: 'Laboratorio' }))

    const dialog = await screen.findByRole('dialog', { name: 'Laboratorio de esta factura' })
    await screen.findByText('b-engine')
    await user.click(within(dialog).getByRole('button', { name: 'Puntuación' }))

    const engines = screen.getAllByText(/-engine$/).map((el) => el.textContent)
    expect(engines).toEqual(['a-engine', 'b-engine'])
  })
})

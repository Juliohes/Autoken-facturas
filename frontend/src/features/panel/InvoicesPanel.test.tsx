// Tests de comportamiento del panel de facturas (S3.1), C13-C16. El cliente de
// API está mockeado: se inyectan las respuestas de `reporting/invoices`,
// `companies` y `download-url` de cada escenario (sin navegador ni backend reales).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { InvoicesPanel } from './InvoicesPanel'
import type { InvoiceEdit, InvoiceRow, PanelPage } from './types'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), PATCH: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const patchMock = api.PATCH as unknown as AsyncMock

function makeEdit(over: Partial<InvoiceEdit> = {}): InvoiceEdit {
  return {
    id: 'e1',
    field: 'total_amount',
    old_value: '121.00',
    new_value: '150.00',
    edited_by: 'user-1',
    edited_at: '2026-08-01T10:00:00Z',
    ...over,
  }
}

function makeRow(over: Partial<InvoiceRow> = {}): InvoiceRow {
  return {
    id: 'inv-1',
    issue_date: '2026-07-01',
    direction: 'recibida',
    counterparty_tax_id: 'B12345678',
    counterparty_name: 'Proveedor SL',
    counterparty_cif_status: 'valid',
    net_amount: '100.00',
    tax_amount: '21.00',
    total_amount: '121.00',
    irpf_amount: null,
    tax_lines: [],
    confirmed_at: '2026-07-21T10:00:00Z',
    confirmed_by: 'user-1',
    uploaded_file_id: 'file-1',
    uploaded_at: '2026-07-20T09:00:00Z',
    ...over,
  }
}

function makePage(items: InvoiceRow[], nextCursor: string | null = null): PanelPage {
  return { items, next_cursor: nextCursor }
}

function mockRoutes({
  panel = makePage([makeRow()]),
  companies = [{ id: 'c1', name: 'Empresa Uno', cif: 'A11111111', status: 'active' }],
  downloadUrl = { url: 'https://minio.local/signed', expires_in: 300 },
  exportBlob = new Blob(['xlsx'], { type: 'application/vnd.ms-excel' }),
  history = [],
}: {
  panel?: PanelPage
  companies?: unknown[]
  downloadUrl?: { url: string; expires_in: number }
  exportBlob?: Blob
  history?: InvoiceEdit[]
} = {}) {
  getMock.mockImplementation((path: string) => {
    // El export vive bajo el mismo prefijo que el panel: se comprueba primero (más específico).
    if (path.includes('/reporting/invoices/export')) {
      return Promise.resolve({ data: exportBlob, error: undefined })
    }
    if (path.includes('/reporting/invoices')) {
      return Promise.resolve({ data: panel, error: undefined })
    }
    if (path.includes('/history')) {
      return Promise.resolve({ data: history, error: undefined })
    }
    if (path.includes('/companies')) {
      return Promise.resolve({ data: companies, error: undefined })
    }
    if (path.includes('download-url')) {
      return Promise.resolve({ data: downloadUrl, error: undefined })
    }
    throw new Error(`ruta no mockeada: ${path}`)
  })
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <InvoicesPanel />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getMock.mockReset()
  patchMock.mockReset()
})

describe('InvoicesPanel (S3.1)', () => {
  it('C13: muestra una fila por factura con proveedor, CIF, fecha, importes, tramos e IRPF', async () => {
    mockRoutes({
      panel: makePage([
        makeRow({
          id: 'inv-1',
          counterparty_name: 'Proveedor Uno',
          net_amount: '100.00',
          tax_amount: '21.00',
          total_amount: '121.00',
          irpf_amount: '15.00',
          tax_lines: [{ iva_pct: '21', base: '100.00', cuota: '21.00' }],
        }),
        makeRow({ id: 'inv-2', counterparty_name: 'Proveedor Dos' }),
      ]),
    })
    renderPanel()

    const rows = await screen.findAllByTestId('invoice-row')
    expect(rows).toHaveLength(2)
    const first = rows[0]
    expect(within(first).getByText('Proveedor Uno')).toBeInTheDocument()
    // Importes (base, IVA, total) y tramos de IVA, no solo el total (hallazgo de auditoría S3.1).
    // Formateados con coma decimal (2026-08-01, a petición de Julio), nunca con punto.
    expect(within(first).getByText('100,00')).toBeInTheDocument()
    expect(within(first).getByText('21,00')).toBeInTheDocument()
    expect(within(first).getByText('121,00')).toBeInTheDocument()
    expect(within(first).getByText('15,00')).toBeInTheDocument()
    expect(within(first).getByTestId('tax-lines')).toHaveTextContent('21% (100,00 → 21,00)')

    expect(screen.getByText('Desde')).toBeInTheDocument()
    expect(screen.getByText('Hasta')).toBeInTheDocument()
    expect(screen.getByText('CIF de contraparte')).toBeInTheDocument()
    expect(screen.getByText('Estado del CIF')).toBeInTheDocument()
    expect(screen.getByText('Empresa')).toBeInTheDocument()
  })

  it('2026-08-01: editar una factura envía el patch con los campos del formulario', async () => {
    mockRoutes({
      panel: makePage([makeRow({ id: 'inv-1', counterparty_name: 'Proveedor SL' })]),
    })
    patchMock.mockResolvedValue({ data: { id: 'inv-1' }, error: undefined })
    const user = userEvent.setup()
    renderPanel()
    const [row] = await screen.findAllByTestId('invoice-row')

    await user.click(within(row).getByRole('button', { name: 'Editar' }))
    const nameInput = within(row).getByLabelText('Proveedor')
    await user.clear(nameInput)
    await user.type(nameInput, 'Proveedor Editado SL')
    await user.click(within(row).getByRole('button', { name: 'Guardar' }))

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith('/api/v1/invoices/{invoice_id}', {
        params: { path: { invoice_id: 'inv-1' } },
        body: {
          counterparty_name: 'Proveedor Editado SL',
          counterparty_tax_id: 'B12345678',
          issue_date: '2026-07-01',
          net_amount: '100.00',
          tax_amount: '21.00',
          total_amount: '121.00',
          irpf_amount: null,
        },
      })
    })
  })

  it('2026-08-01: "Historial" muestra las ediciones de la factura (antes → después)', async () => {
    mockRoutes({
      panel: makePage([makeRow({ id: 'inv-1' })]),
      history: [makeEdit({ field: 'total_amount', old_value: '121.00', new_value: '150.00' })],
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')

    await user.click(screen.getByRole('button', { name: 'Historial' }))

    const rows = await screen.findAllByTestId('invoice-history-row')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent('121,00')
    expect(rows[0]).toHaveTextContent('150,00')
  })

  it('2026-08-01: "Revertir a este valor" envía un PATCH con el valor anterior de ese campo', async () => {
    mockRoutes({
      panel: makePage([makeRow({ id: 'inv-1', total_amount: '150.00' })]),
      history: [makeEdit({ field: 'total_amount', old_value: '121.00', new_value: '150.00' })],
    })
    patchMock.mockResolvedValue({ data: { id: 'inv-1' }, error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')

    await user.click(screen.getByRole('button', { name: 'Historial' }))
    await user.click(await screen.findByRole('button', { name: 'Revertir a este valor' }))

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith('/api/v1/invoices/{invoice_id}', {
        params: { path: { invoice_id: 'inv-1' } },
        body: { total_amount: '121.00' },
      })
    })
  })

  it('C14: el botón "Ver" pide la URL firmada y la abre en una pestaña nueva', async () => {
    mockRoutes()
    const user = userEvent.setup()
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)
    renderPanel()

    await user.click(await screen.findByRole('button', { name: 'Ver' }))

    await waitFor(() => {
      expect(getMock).toHaveBeenCalledWith(
        '/api/v1/uploads/{file_id}/download-url',
        expect.objectContaining({ params: { path: { file_id: 'file-1' } } }),
      )
    })
    expect(openSpy).toHaveBeenCalledWith(
      'https://minio.local/signed',
      '_blank',
      'noopener,noreferrer',
    )
    openSpy.mockRestore()
  })

  it('C10: "Descargar Excel" pide el export con los filtros aplicados (sin cursor)', async () => {
    mockRoutes()
    const user = userEvent.setup()
    const createObjectURLSpy = vi
      .spyOn(URL, 'createObjectURL')
      .mockReturnValue('blob:mock-url')
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {})
    renderPanel()
    await screen.findAllByTestId('invoice-row')

    await user.click(screen.getByRole('button', { name: 'Descargar Excel' }))

    await waitFor(() => {
      expect(getMock).toHaveBeenCalledWith(
        '/api/v1/reporting/invoices/export',
        expect.objectContaining({ params: { query: {} }, parseAs: 'blob' }),
      )
    })
    expect(clickSpy).toHaveBeenCalledTimes(1)
    expect(createObjectURLSpy).toHaveBeenCalledTimes(1)
    expect(revokeObjectURLSpy).toHaveBeenCalledTimes(1)

    createObjectURLSpy.mockRestore()
    revokeObjectURLSpy.mockRestore()
    clickSpy.mockRestore()
  })

  it('C15: "Cargar más" añade filas sin perder las ya visibles', async () => {
    getMock.mockImplementation((path: string, opts: { params?: { query?: { cursor?: string } } }) => {
      if (path.includes('/reporting/invoices')) {
        const cursor = opts?.params?.query?.cursor
        if (!cursor) {
          return Promise.resolve({
            data: makePage([makeRow({ id: 'inv-1' })], 'cursor-2'),
            error: undefined,
          })
        }
        return Promise.resolve({ data: makePage([makeRow({ id: 'inv-2' })], null), error: undefined })
      }
      if (path.includes('/companies')) return Promise.resolve({ data: [], error: undefined })
      throw new Error(`ruta no mockeada: ${path}`)
    })
    const user = userEvent.setup()
    renderPanel()

    expect(await screen.findAllByTestId('invoice-row')).toHaveLength(1)
    const loadMore = screen.getByRole('button', { name: 'Cargar más' })
    await user.click(loadMore)

    await waitFor(() => expect(screen.getAllByTestId('invoice-row')).toHaveLength(2))
    expect(screen.queryByRole('button', { name: 'Cargar más' })).not.toBeInTheDocument()
  })

  it('C16: muestra "Cargando…" mientras carga', () => {
    getMock.mockReturnValue(new Promise(() => {})) // nunca resuelve: estado de carga estable
    renderPanel()

    expect(screen.getByText('Cargando…')).toBeInTheDocument()
  })

  it('C16: lista vacía muestra el mensaje de "no hay facturas", no una tabla vacía', async () => {
    mockRoutes({ panel: makePage([]) })
    renderPanel()

    expect(await screen.findByText('No hay facturas con estos filtros.')).toBeInTheDocument()
    expect(screen.queryByTestId('invoices-table')).not.toBeInTheDocument()
  })

  it('C16: muestra un error legible si falla, sin datos a medias', async () => {
    getMock.mockImplementation((path: string) => {
      if (path.includes('/reporting/invoices')) {
        return Promise.resolve({ data: undefined, error: { detail: 'boom' } })
      }
      return Promise.resolve({ data: [], error: undefined })
    })
    renderPanel()

    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudo cargar/i)
    expect(screen.queryByTestId('invoices-table')).not.toBeInTheDocument()
  })
})

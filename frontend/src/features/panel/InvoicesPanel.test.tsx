// Tests de comportamiento del panel de facturas (S3.1 + ampliación 2026-08-01). El cliente de API
// está mockeado: se inyectan las respuestas de `reporting/invoices`, `companies`,
// `uploads/{id}/image` y `invoices/{id}` de cada escenario (sin navegador ni backend reales).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { InvoicesPanel } from './InvoicesPanel'
import type { InvoiceRow, PanelPage } from './types'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), PATCH: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const patchMock = api.PATCH as unknown as AsyncMock

function makeRow(over: Partial<InvoiceRow> = {}): InvoiceRow {
  return {
    id: 'inv-1',
    company_name: 'Empresa Cliente SL',
    company_cif: 'C99999999',
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
  imageBlob = new Blob(['foto'], { type: 'image/jpeg' }),
  exportBlob = new Blob(['xlsx'], { type: 'application/vnd.ms-excel' }),
}: {
  panel?: PanelPage
  companies?: unknown[]
  imageBlob?: Blob
  exportBlob?: Blob
} = {}) {
  getMock.mockImplementation((path: string) => {
    // El export vive bajo el mismo prefijo que el panel: se comprueba primero (más específico).
    if (path.includes('/reporting/invoices/export')) {
      return Promise.resolve({ data: exportBlob, error: undefined })
    }
    if (path.includes('/reporting/invoices')) {
      return Promise.resolve({ data: panel, error: undefined })
    }
    if (path.includes('/companies')) {
      return Promise.resolve({ data: companies, error: undefined })
    }
    if (path.includes('/image')) {
      return Promise.resolve({ data: imageBlob, error: undefined })
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
  it('C13: muestra una fila por factura con empresa cliente, proveedor, CIF, fecha, importes e IRPF', async () => {
    mockRoutes({
      panel: makePage([
        makeRow({
          id: 'inv-1',
          company_name: 'Mi Empresa SL',
          company_cif: 'C11111111',
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
    expect(within(first).getByText('Mi Empresa SL')).toBeInTheDocument()
    expect(within(first).getByText('C11111111')).toBeInTheDocument()
    expect(within(first).getByText('Proveedor Uno')).toBeInTheDocument()
    // Importes (base, IVA, total) e IRPF, no solo el total (hallazgo de auditoría S3.1).
    // Formateados con coma decimal (2026-08-01, a petición de Julio), nunca con punto.
    expect(within(first).getByText('100,00')).toBeInTheDocument()
    expect(within(first).getByText('21,00')).toBeInTheDocument()
    expect(within(first).getByText('121,00')).toBeInTheDocument()
    expect(within(first).getByText('15,00')).toBeInTheDocument()
    // Tramos de IVA: un botón con el número de tramos, no texto (2026-08-01).
    expect(within(first).getByRole('button', { name: '1 tramo' })).toBeInTheDocument()

    expect(screen.getByText('Desde')).toBeInTheDocument()
    expect(screen.getByText('Hasta')).toBeInTheDocument()
    expect(screen.getByText('CIF de contraparte')).toBeInTheDocument()
    expect(screen.getByText('Estado del CIF')).toBeInTheDocument()
    expect(screen.getByLabelText('Empresa')).toBeInTheDocument() // filtro (el <th> también dice "Empresa")
  })

  it('2026-08-01: sin tramos de IVA, el botón dice "Sin tramos"', async () => {
    mockRoutes({ panel: makePage([makeRow({ tax_lines: [] })]) })
    renderPanel()

    expect(
      await screen.findByRole('button', { name: 'Sin tramos' }),
    ).toBeInTheDocument()
  })

  it('2026-08-01: "Editar" es un único botón que activa la edición de todas las filas a la vez', async () => {
    mockRoutes({
      panel: makePage([
        makeRow({ id: 'inv-1', counterparty_name: 'Uno' }),
        makeRow({ id: 'inv-2', counterparty_name: 'Dos' }),
      ]),
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')

    // Un único botón "Editar" en toda la pantalla (no uno por fila).
    expect(screen.getAllByRole('button', { name: 'Editar' })).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Editar' }))

    // Al activarlo, TODAS las filas muestran a la vez el campo "Proveedor" como input editable.
    expect(screen.getAllByLabelText('Proveedor')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Terminar edición' })).toBeInTheDocument()
  })

  it('2026-08-01: cada celda se guarda sola al perder el foco, sin un botón Guardar por fila', async () => {
    mockRoutes({
      panel: makePage([makeRow({ id: 'inv-1', counterparty_name: 'Proveedor SL' })]),
    })
    patchMock.mockResolvedValue({ data: { id: 'inv-1' }, error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')
    await user.click(screen.getByRole('button', { name: 'Editar' }))

    const nameInput = screen.getByLabelText('Proveedor')
    await user.clear(nameInput)
    await user.type(nameInput, 'Proveedor Editado SL')
    await user.tab() // pierde el foco -> guarda

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith('/api/v1/invoices/{invoice_id}', {
        params: { path: { invoice_id: 'inv-1' } },
        body: { counterparty_name: 'Proveedor Editado SL' },
      })
    })
  })

  it('2026-08-01: perder el foco sin cambiar el valor no llama al PATCH', async () => {
    mockRoutes({
      panel: makePage([makeRow({ id: 'inv-1', counterparty_name: 'Proveedor SL' })]),
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')
    await user.click(screen.getByRole('button', { name: 'Editar' }))

    await user.click(screen.getByLabelText('Proveedor'))
    await user.tab()

    expect(patchMock).not.toHaveBeenCalled()
  })

  it('2026-08-08: las celdas de importe se editan con coma decimal, nunca con punto', async () => {
    mockRoutes({
      panel: makePage([makeRow({ id: 'inv-1', net_amount: '100.00' })]),
    })
    patchMock.mockResolvedValue({ data: { id: 'inv-1' }, error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')
    await user.click(screen.getByRole('button', { name: 'Editar' }))

    // El valor inicial se muestra con coma (hallazgo de Julio: seguía mostrando "100.00").
    const baseInput = screen.getByLabelText('Base')
    expect(baseInput).toHaveValue('100,00')

    // Editar con coma se envía al backend con punto (lo que espera `Decimal`).
    await user.clear(baseInput)
    await user.type(baseInput, '150,50')
    await user.tab()

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith('/api/v1/invoices/{invoice_id}', {
        params: { path: { invoice_id: 'inv-1' } },
        body: { net_amount: '150.50' },
      })
    })
  })

  it('2026-08-01: "Ver" muestra la foto original en una ventana, no abre una URL de MinIO', async () => {
    mockRoutes({ imageBlob: new Blob(['contenido-foto'], { type: 'image/jpeg' }) })
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:foto-mock')
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')

    await user.click(screen.getByRole('button', { name: 'Ver' }))

    await waitFor(() => {
      expect(getMock).toHaveBeenCalledWith(
        '/api/v1/uploads/{file_id}/image',
        expect.objectContaining({ params: { path: { file_id: 'file-1' } }, parseAs: 'blob' }),
      )
    })
    const dialog = await screen.findByRole('dialog', { name: 'Foto de la factura' })
    expect(within(dialog).getByRole('img', { name: 'Foto original de la factura' })).toHaveAttribute(
      'src',
      'blob:foto-mock',
    )

    await user.click(within(dialog).getByRole('button', { name: 'Cerrar' }))
    expect(screen.queryByRole('dialog', { name: 'Foto de la factura' })).not.toBeInTheDocument()
    createObjectURLSpy.mockRestore()
  })

  it('2026-08-01: el botón de tramos abre una ventana donde cada tramo es editable', async () => {
    mockRoutes({
      panel: makePage([
        makeRow({ id: 'inv-1', tax_lines: [{ iva_pct: '21', base: '100.00', cuota: '21.00' }] }),
      ]),
    })
    patchMock.mockResolvedValue({ data: { id: 'inv-1' }, error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')

    await user.click(screen.getByRole('button', { name: '1 tramo' }))
    const dialog = await screen.findByRole('dialog', { name: 'Tramos de IVA' })
    const baseInput = within(dialog).getByLabelText('Tramo 1: Base')
    await user.clear(baseInput)
    await user.type(baseInput, '200.00')
    await user.click(within(dialog).getByRole('button', { name: 'Guardar' }))

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith('/api/v1/invoices/{invoice_id}', {
        params: { path: { invoice_id: 'inv-1' } },
        body: {
          tax_lines: [{ iva_pct: '21', base: '200.00', cuota: '21.00' }],
        },
      })
    })
    expect(screen.queryByRole('dialog', { name: 'Tramos de IVA' })).not.toBeInTheDocument()
  })

  it('2026-08-08: la ventana de tramos muestra base/cuota con coma, y tolera editar con coma', async () => {
    mockRoutes({
      panel: makePage([
        makeRow({ id: 'inv-1', tax_lines: [{ iva_pct: '21', base: '100.00', cuota: '21.00' }] }),
      ]),
    })
    patchMock.mockResolvedValue({ data: { id: 'inv-1' }, error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')

    await user.click(screen.getByRole('button', { name: '1 tramo' }))
    const dialog = await screen.findByRole('dialog', { name: 'Tramos de IVA' })
    // Valor inicial con coma (hallazgo de Julio: esta ventana seguía mostrando "100.00").
    expect(within(dialog).getByLabelText('Tramo 1: Base')).toHaveValue('100,00')
    expect(within(dialog).getByLabelText('Tramo 1: Cuota')).toHaveValue('21,00')

    const cuotaInput = within(dialog).getByLabelText('Tramo 1: Cuota')
    await user.clear(cuotaInput)
    await user.type(cuotaInput, '25,50')
    await user.click(within(dialog).getByRole('button', { name: 'Guardar' }))

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith('/api/v1/invoices/{invoice_id}', {
        params: { path: { invoice_id: 'inv-1' } },
        body: {
          tax_lines: [{ iva_pct: '21', base: '100.00', cuota: '25.50' }],
        },
      })
    })
  })

  it('C10: "Descargar Excel" pide el export con los filtros aplicados (sin cursor)', async () => {
    mockRoutes()
    const user = userEvent.setup()
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-url')
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
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

  it('S6.2 C3: el panel del tenant nunca muestra un botón/enlace "Laboratorio" (vive solo en plataforma)', async () => {
    mockRoutes()
    renderPanel()

    await screen.findAllByTestId('invoice-row')

    // El laboratorio S6.2 es exclusivo del panel de plataforma (admin-tech): este panel de tenant
    // no debe ganar NADA nuevo, sin importar quién lo mire (no depende de `is_admin_tech`, este
    // componente ni siquiera consulta la sesión).
    expect(screen.queryByText(/laboratorio/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /laboratorio/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /laboratorio/i })).not.toBeInTheDocument()
  })

  it('2026-08-10: las columnas se pueden redimensionar arrastrando, sin tener que pulsar "Editar" antes', async () => {
    mockRoutes()
    renderPanel()
    await screen.findAllByTestId('invoice-row')

    // Sin pulsar "Editar": el asa ya está en el DOM y usable (mismo criterio que CompaniesPanel).
    const handle = screen.getByRole('separator', { name: 'Redimensionar columna Empresa' })
    const header = screen.getByRole('button', { name: 'Empresa' }).closest('th') as HTMLElement
    const startWidth = Number(header.style.width.replace('px', ''))

    fireEvent.mouseDown(handle, { clientX: 100 })
    fireEvent.mouseMove(document, { clientX: 150 })
    fireEvent.mouseUp(document)

    expect(Number(header.style.width.replace('px', ''))).toBe(startWidth + 50)
  })

  it('2026-08-10: pulsar la cabecera "Empresa" ordena las filas alfabéticamente, como en Excel', async () => {
    mockRoutes({
      panel: makePage([
        makeRow({ id: 'inv-1', company_name: 'Zeta SL' }),
        makeRow({ id: 'inv-2', company_name: 'Alfa SL' }),
      ]),
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')

    const namesInOrder = () =>
      screen.getAllByTestId('invoice-row').map((row) => within(row).getAllByRole('cell')[0].textContent)
    expect(namesInOrder()).toEqual(['Zeta SL', 'Alfa SL'])

    await user.click(screen.getByRole('button', { name: 'Empresa' }))
    expect(namesInOrder()).toEqual(['Alfa SL', 'Zeta SL'])
  })

  it('2026-08-10: ordenar por "Total" compara importes por valor numérico, no como texto', async () => {
    mockRoutes({
      panel: makePage([
        makeRow({ id: 'inv-1', company_name: 'A', total_amount: '9.00' }),
        makeRow({ id: 'inv-2', company_name: 'B', total_amount: '10.00' }),
        makeRow({ id: 'inv-3', company_name: 'C', total_amount: '2.00' }),
      ]),
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('invoice-row')

    await user.click(screen.getByRole('button', { name: 'Total' }))

    const namesInOrder = screen
      .getAllByTestId('invoice-row')
      .map((row) => within(row).getAllByRole('cell')[0].textContent)
    // Orden numérico correcto (2, 9, 10): un orden como texto habría puesto "10.00" antes que "2.00".
    expect(namesInOrder).toEqual(['C', 'A', 'B'])
  })
})

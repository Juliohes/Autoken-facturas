// Tests de comportamiento de la pantalla "Empresas" (S3.4 + rediseño 2026-08-09). El cliente de
// API está mockeado: se inyectan las respuestas de `reporting/companies`, `companies` y
// `registrations` de cada escenario (sin navegador ni backend reales; jsdom).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { CompaniesPanel } from './CompaniesPanel'
import type { CompanyRow, PendingRegistration } from './types'

vi.mock('../../api/client', () => ({
  api: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn(), DELETE: vi.fn() },
}))

type AsyncMock = Mock<(...args: never[]) => Promise<unknown>>
const getMock = api.GET as unknown as AsyncMock
const postMock = api.POST as unknown as AsyncMock
const patchMock = api.PATCH as unknown as AsyncMock
const deleteMock = api.DELETE as unknown as AsyncMock

function makeCompany(over: Partial<CompanyRow> = {}): CompanyRow {
  return {
    id: 'c1',
    name: 'Empresa Uno',
    cif: 'A11111111',
    status: 'active',
    notes: null,
    created_at: '2026-01-01T00:00:00Z',
    user_count: 2,
    invoice_count: 5,
    last_invoice_at: '2026-07-01T00:00:00Z',
    ...over,
  }
}

function makeRegistration(over: Partial<PendingRegistration> = {}): PendingRegistration {
  return {
    id: 'u1',
    email: 'nuevo@ilex.es',
    company: 'Empresa Nueva',
    joins_existing_company: false,
    ...over,
  }
}

function mockRoutes({
  companies = [makeCompany()],
  registrations = [],
}: {
  companies?: CompanyRow[]
  registrations?: PendingRegistration[]
} = {}) {
  getMock.mockImplementation((path: string) => {
    if (path.includes('/reporting/companies')) {
      return Promise.resolve({ data: companies, error: undefined })
    }
    if (path.includes('/registrations')) {
      return Promise.resolve({ data: registrations, error: undefined })
    }
    throw new Error(`ruta GET no mockeada: ${path}`)
  })
}

function renderPanel(onViewInvoices?: (companyId: string) => void) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <CompaniesPanel onViewInvoices={onViewInvoices} />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  patchMock.mockReset()
  deleteMock.mockReset()
  localStorage.clear()
})

describe('CompaniesPanel (S3.4)', () => {
  it('C1: muestra una fila por empresa con sus contadores, notas y fecha de alta', async () => {
    mockRoutes({
      companies: [
        makeCompany({ name: 'Empresa Uno', notes: 'cliente VIP', user_count: 3, invoice_count: 7 }),
      ],
    })
    renderPanel()

    const rows = await screen.findAllByTestId('company-row')
    expect(rows).toHaveLength(1)
    const row = rows[0]
    expect(within(row).getByText('Empresa Uno')).toBeInTheDocument()
    expect(within(row).getByText('cliente VIP')).toBeInTheDocument()
    expect(within(row).getByText('3')).toBeInTheDocument()
    expect(within(row).getByText('7')).toBeInTheDocument()
  })

  it('C2: crear una empresa envía el alta con nombre, CIF y notas', async () => {
    mockRoutes({ companies: [] })
    postMock.mockResolvedValue({
      data: { id: 'c2', name: 'Nueva SL', cif: 'B22222222', status: 'active' },
      error: undefined,
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Todavía no hay empresas.')

    await user.type(screen.getByLabelText('Nombre'), 'Nueva SL')
    await user.type(screen.getByLabelText('CIF'), 'B22222222')
    await user.type(screen.getByLabelText('Notas'), 'alta de prueba')
    await user.click(screen.getByRole('button', { name: 'Nueva empresa' }))

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('/api/v1/companies', {
        body: { name: 'Nueva SL', cif: 'B22222222', notes: 'alta de prueba' },
      })
    })
  })

  it('2026-08-09: la fila solo tiene "Ver facturas" — nada de Editar/Borrar/Historial por fila', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1' })] })
    renderPanel()
    const [row] = await screen.findAllByTestId('company-row')

    expect(within(row).getByRole('button', { name: 'Ver facturas' })).toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: 'Editar' })).not.toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: 'Borrar' })).not.toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: 'Historial' })).not.toBeInTheDocument()
  })

  it('2026-08-09: "Editar" activa la edición de todas las filas a la vez, junto a "Nueva empresa"', async () => {
    mockRoutes({
      companies: [
        makeCompany({ id: 'c1', name: 'Uno' }),
        makeCompany({ id: 'c2', name: 'Dos' }),
      ],
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    expect(screen.getAllByRole('button', { name: 'Editar' })).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Editar' }))

    const rows = screen.getAllByTestId('company-row')
    expect(rows).toHaveLength(2)
    for (const row of rows) {
      expect(within(row).getByLabelText('Nombre')).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: 'Terminar edición' })).toBeInTheDocument()
  })

  it('2026-08-09: cada celda editable se guarda sola al perder el foco, con patch parcial', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1', name: 'Empresa Uno' })] })
    patchMock.mockResolvedValue({ data: makeCompany({ name: 'Empresa Editada' }), error: undefined })
    const user = userEvent.setup()
    renderPanel()
    const [row] = await screen.findAllByTestId('company-row')
    await user.click(screen.getByRole('button', { name: 'Editar' }))

    const nameInput = within(row).getByLabelText('Nombre')
    await user.clear(nameInput)
    await user.type(nameInput, 'Empresa Editada')
    await user.tab()

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith('/api/v1/companies/{company_id}', {
        params: { path: { company_id: 'c1' } },
        body: { name: 'Empresa Editada' },
      })
    })
  })

  it('2026-08-09: perder el foco sin cambiar el valor no llama al PATCH', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1', name: 'Empresa Uno' })] })
    const user = userEvent.setup()
    renderPanel()
    const [row] = await screen.findAllByTestId('company-row')
    await user.click(screen.getByRole('button', { name: 'Editar' }))

    await user.click(within(row).getByLabelText('Nombre'))
    await user.tab()

    expect(patchMock).not.toHaveBeenCalled()
  })

  it('2026-08-09: "Borrar" muestra una casilla por fila, sin edición a la vez', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1', name: 'Empresa Uno' })] })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))

    expect(screen.getByLabelText('Seleccionar Empresa Uno')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Cancelar' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Editar' })).toBeDisabled()
  })

  it('2026-08-09: seleccionar empresas y confirmar el borrado múltiple llama al DELETE de cada una', async () => {
    mockRoutes({
      companies: [
        makeCompany({ id: 'c1', name: 'Uno' }),
        makeCompany({ id: 'c2', name: 'Dos' }),
      ],
    })
    deleteMock.mockResolvedValue({ data: undefined, error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))
    await user.click(screen.getByLabelText('Seleccionar Uno'))
    await user.click(screen.getByLabelText('Seleccionar Dos'))
    await user.click(screen.getByRole('button', { name: 'Borrar seleccionadas (2)' }))

    const dialog = await screen.findByRole('dialog', { name: 'Confirmar borrado de empresas' })
    expect(within(dialog).getByText('Uno')).toBeInTheDocument()
    expect(within(dialog).getByText('Dos')).toBeInTheDocument()

    await user.click(within(dialog).getByRole('button', { name: 'Borrar' }))

    await waitFor(() => {
      expect(deleteMock).toHaveBeenCalledWith('/api/v1/companies/{company_id}', {
        params: { path: { company_id: 'c1' } },
      })
      expect(deleteMock).toHaveBeenCalledWith('/api/v1/companies/{company_id}', {
        params: { path: { company_id: 'c2' } },
      })
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('2026-08-09: sin seleccionar ninguna, "Borrar seleccionadas" está deshabilitado', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1' })] })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))

    expect(screen.getByRole('button', { name: 'Borrar seleccionadas (0)' })).toBeDisabled()
  })

  it('2026-08-09: cancelar el aviso de confirmación no borra nada', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1', name: 'Uno' })] })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))
    await user.click(screen.getByLabelText('Seleccionar Uno'))
    await user.click(screen.getByRole('button', { name: 'Borrar seleccionadas (1)' }))
    const dialog = await screen.findByRole('dialog', { name: 'Confirmar borrado de empresas' })
    await user.click(within(dialog).getByRole('button', { name: 'Cancelar' }))

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(deleteMock).not.toHaveBeenCalled()
  })

  it('2026-08-09: borrar una empresa con usuarios muestra el motivo del 409, sin desaparecer en silencio', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1', name: 'Uno' })] })
    deleteMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'La empresa tiene usuarios asignados: reasígnalos o quítalos antes de borrarla' },
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))
    await user.click(screen.getByLabelText('Seleccionar Uno'))
    await user.click(screen.getByRole('button', { name: 'Borrar seleccionadas (1)' }))
    const dialog = await screen.findByRole('dialog', { name: 'Confirmar borrado de empresas' })
    await user.click(within(dialog).getByRole('button', { name: 'Borrar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/no se pudieron borrar: uno/i)
  })

  it('2026-08-09: al confirmar y borrar con éxito, la fila desaparece de verdad de la tabla', async () => {
    let companies = [makeCompany({ id: 'c1', name: 'Uno' })]
    getMock.mockImplementation((path: string) => {
      if (path.includes('/reporting/companies')) {
        return Promise.resolve({ data: companies, error: undefined })
      }
      if (path.includes('/registrations')) return Promise.resolve({ data: [], error: undefined })
      throw new Error(`ruta GET no mockeada: ${path}`)
    })
    deleteMock.mockImplementation(async () => {
      companies = []
      return { data: undefined, error: undefined }
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))
    await user.click(screen.getByLabelText('Seleccionar Uno'))
    await user.click(screen.getByRole('button', { name: 'Borrar seleccionadas (1)' }))
    const dialog = await screen.findByRole('dialog', { name: 'Confirmar borrado de empresas' })
    await user.click(within(dialog).getByRole('button', { name: 'Borrar' }))

    await waitFor(() => expect(screen.queryByTestId('company-row')).not.toBeInTheDocument())
    expect(await screen.findByText('Todavía no hay empresas.')).toBeInTheDocument()
  })

  it('C5: "Ver facturas" llama al callback con el id de la empresa', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1' })] })
    const onViewInvoices = vi.fn()
    const user = userEvent.setup()
    renderPanel(onViewInvoices)
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Ver facturas' }))

    expect(onViewInvoices).toHaveBeenCalledWith('c1')
  })

  it('C6: lista los registros pendientes con su empresa y la señal de empresa existente', async () => {
    mockRoutes({
      companies: [],
      registrations: [
        makeRegistration({ email: 'a@ilex.es', company: 'Empresa X', joins_existing_company: true }),
      ],
    })
    renderPanel()

    const row = await screen.findByTestId('registration-row')
    expect(within(row).getByText('a@ilex.es')).toBeInTheDocument()
    expect(within(row).getByText('Empresa X')).toBeInTheDocument()
    expect(within(row).getByText(/se une a empresa existente/)).toBeInTheDocument()
  })

  it('C7: aprobar un registro llama al endpoint de aprobación', async () => {
    mockRoutes({ companies: [], registrations: [makeRegistration({ id: 'u1' })] })
    postMock.mockResolvedValue({ data: { status: 'active' }, error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByTestId('registration-row')

    await user.click(screen.getByRole('button', { name: 'Aprobar' }))

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('/api/v1/registrations/{user_id}/approve', {
        params: { path: { user_id: 'u1' } },
      })
    })
  })

  it('C8: rechazar un registro llama al endpoint de rechazo', async () => {
    mockRoutes({ companies: [], registrations: [makeRegistration({ id: 'u1' })] })
    postMock.mockResolvedValue({ data: undefined, error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findByTestId('registration-row')

    await user.click(screen.getByRole('button', { name: 'Rechazar' }))

    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('/api/v1/registrations/{user_id}/reject', {
        params: { path: { user_id: 'u1' } },
      })
    })
  })

  it('C9: sin empresas ni registros pendientes muestra los mensajes de vacío, no tablas vacías', async () => {
    mockRoutes({ companies: [], registrations: [] })
    renderPanel()

    expect(await screen.findByText('Todavía no hay empresas.')).toBeInTheDocument()
    expect(screen.getByText('No hay registros pendientes.')).toBeInTheDocument()
    expect(screen.queryByTestId('companies-table')).not.toBeInTheDocument()
    expect(screen.queryByTestId('registrations-table')).not.toBeInTheDocument()
  })

  it('C10 (S3.5): purgar pide confirmación nativa y muestra cuántas facturas se borraron', async () => {
    mockRoutes({ companies: [], registrations: [] })
    postMock.mockResolvedValue({ data: { purged: 3 }, error: undefined })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Todavía no hay empresas.')

    await user.click(screen.getByRole('button', { name: 'Purgar facturas de prueba' }))

    expect(confirmSpy).toHaveBeenCalled()
    await waitFor(() => {
      expect(postMock).toHaveBeenCalledWith('/api/v1/invoices/test/purge')
    })
    expect(await screen.findByText('Se han borrado 3 facturas de prueba.')).toBeInTheDocument()
    confirmSpy.mockRestore()
  })

  it('C11 (S3.5): cancelar el diálogo nativo no llama al endpoint de purga', async () => {
    mockRoutes({ companies: [], registrations: [] })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    renderPanel()
    await screen.findByText('Todavía no hay empresas.')

    await user.click(screen.getByRole('button', { name: 'Purgar facturas de prueba' }))

    expect(confirmSpy).toHaveBeenCalled()
    expect(postMock).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('2026-08-09: las columnas empiezan estrechas por defecto, sobre todo "Notas"', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1' })] })
    renderPanel()
    await screen.findAllByTestId('company-row')

    const notesHeader = screen.getByText('Notas', { selector: 'th span' }).closest('th')
    const nameHeader = screen.getByText('Nombre', { selector: 'th span' }).closest('th')
    const notesWidth = Number(notesHeader?.style.width.replace('px', ''))
    const nameWidth = Number(nameHeader?.style.width.replace('px', ''))
    expect(notesWidth).toBeLessThan(nameWidth)
  })

  it('2026-08-09: arrastrar el asa de una columna cambia su ancho y lo recuerda al recargar', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1' })] })
    renderPanel()
    await screen.findAllByTestId('company-row')

    const handle = screen.getByRole('separator', { name: 'Redimensionar columna Nombre' })
    const header = screen.getByText('Nombre', { selector: 'th span' }).closest('th') as HTMLElement
    const startWidth = Number(header.style.width.replace('px', ''))

    fireEvent.mouseDown(handle, { clientX: 100 })
    fireEvent.mouseMove(document, { clientX: 180 })
    fireEvent.mouseUp(document)

    const newWidth = Number(header.style.width.replace('px', ''))
    expect(newWidth).toBe(startWidth + 80)
    expect(JSON.parse(localStorage.getItem('companies-panel-column-widths') ?? '{}').name).toBe(
      newWidth,
    )

    // "Recuerda al recargar": una nueva instancia del panel (simula recargar la página) lee el
    // ancho ya guardado en este navegador, en vez de volver siempre al valor por defecto.
    const { unmount } = render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <CompaniesPanel />
      </QueryClientProvider>,
    )
    const newHeaders = await screen.findAllByText('Nombre', { selector: 'th span' })
    const newHeader = newHeaders[newHeaders.length - 1].closest('th') as HTMLElement
    expect(Number(newHeader.style.width.replace('px', ''))).toBe(newWidth)
    unmount()
  })
})

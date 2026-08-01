// Tests de comportamiento de la pantalla "Empresas" (S3.4), C1-C9 (frontend). El cliente de API
// está mockeado: se inyectan las respuestas de `reporting/companies`, `companies` y
// `registrations` de cada escenario (sin navegador ni backend reales; jsdom).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest'

import { api } from '../../api/client'
import { CompaniesPanel } from './CompaniesPanel'
import type { CompanyEdit, CompanyRow, PendingRegistration } from './types'

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

function makeEdit(over: Partial<CompanyEdit> = {}): CompanyEdit {
  return {
    id: 'e1',
    field: 'name',
    old_value: 'Antes SL',
    new_value: 'Después SL',
    edited_by: 'u1',
    edited_at: '2026-08-01T10:00:00Z',
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
  history = [],
}: {
  companies?: CompanyRow[]
  registrations?: PendingRegistration[]
  history?: CompanyEdit[]
} = {}) {
  getMock.mockImplementation((path: string) => {
    if (path.includes('/reporting/companies')) {
      return Promise.resolve({ data: companies, error: undefined })
    }
    if (path.includes('/registrations')) {
      return Promise.resolve({ data: registrations, error: undefined })
    }
    if (path.includes('/history')) {
      return Promise.resolve({ data: history, error: undefined })
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

  it('C3: editar una empresa envía el patch con los campos cambiados', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1', name: 'Empresa Uno' })] })
    patchMock.mockResolvedValue({ data: makeCompany({ name: 'Empresa Editada' }), error: undefined })
    const user = userEvent.setup()
    renderPanel()
    const [row] = await screen.findAllByTestId('company-row')

    await user.click(within(row).getByRole('button', { name: 'Editar' }))
    const nameInput = within(row).getByLabelText('Nombre')
    await user.clear(nameInput)
    await user.type(nameInput, 'Empresa Editada')
    await user.click(within(row).getByRole('button', { name: 'Guardar' }))

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith('/api/v1/companies/{company_id}', {
        params: { path: { company_id: 'c1' } },
        body: { name: 'Empresa Editada', cif: 'A11111111', notes: null, status: 'active' },
      })
    })
  })

  it('C4: borrar una empresa con usuarios muestra el motivo del 409, sin desaparecer en silencio', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1' })] })
    deleteMock.mockResolvedValue({
      data: undefined,
      error: { detail: 'La empresa tiene usuarios asignados: reasígnalos o quítalos antes de borrarla' },
    })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/usuarios asignados/)
    expect(deleteMock).toHaveBeenCalledWith('/api/v1/companies/{company_id}', {
      params: { path: { company_id: 'c1' } },
    })
    confirmSpy.mockRestore()
  })

  it('C12: borrar pide confirmación nativa, con el nombre de la empresa, antes de llamar al endpoint', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1', name: 'Empresa Uno' })] })
    deleteMock.mockResolvedValue({ data: undefined, error: undefined })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))

    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('Empresa Uno'))
    await waitFor(() => expect(deleteMock).toHaveBeenCalled())
    confirmSpy.mockRestore()
  })

  it('C13: cancelar el diálogo de confirmación no llama al borrado', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1' })] })
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))

    expect(confirmSpy).toHaveBeenCalled()
    expect(deleteMock).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('C14: al confirmar y borrar con éxito, la fila desaparece de verdad de la tabla', async () => {
    let companies = [makeCompany({ id: 'c1', name: 'Empresa Uno' })]
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
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Borrar' }))

    await waitFor(() => expect(screen.queryByTestId('company-row')).not.toBeInTheDocument())
    expect(await screen.findByText('Todavía no hay empresas.')).toBeInTheDocument()
    confirmSpy.mockRestore()
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

  it('2026-08-01: "Historial" muestra las ediciones de la empresa (antes → después)', async () => {
    mockRoutes({
      companies: [makeCompany({ id: 'c1' })],
      history: [
        makeEdit({ field: 'name', old_value: 'Antes SL', new_value: 'Después SL' }),
        makeEdit({ id: 'e2', field: 'cif', old_value: 'A11111111', new_value: 'B22222222' }),
      ],
    })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Historial' }))

    const rows = await screen.findAllByTestId('company-history-row')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Antes SL')
    expect(rows[0]).toHaveTextContent('Después SL')
  })

  it('2026-08-01: sin ediciones, el historial dice que no hay nada registrado todavía', async () => {
    mockRoutes({ companies: [makeCompany({ id: 'c1' })], history: [] })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Historial' }))

    expect(
      await screen.findByText('Todavía no hay ediciones registradas.'),
    ).toBeInTheDocument()
  })

  it('2026-08-01: "Revertir a este valor" envía un PATCH con el valor anterior de ese campo', async () => {
    mockRoutes({
      companies: [makeCompany({ id: 'c1', name: 'Después SL' })],
      history: [makeEdit({ field: 'name', old_value: 'Antes SL', new_value: 'Después SL' })],
    })
    patchMock.mockResolvedValue({ data: makeCompany({ name: 'Antes SL' }), error: undefined })
    const user = userEvent.setup()
    renderPanel()
    await screen.findAllByTestId('company-row')

    await user.click(screen.getByRole('button', { name: 'Historial' }))
    await user.click(await screen.findByRole('button', { name: 'Revertir a este valor' }))

    await waitFor(() => {
      expect(patchMock).toHaveBeenCalledWith('/api/v1/companies/{company_id}', {
        params: { path: { company_id: 'c1' } },
        body: { name: 'Antes SL' },
      })
    })
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
})
